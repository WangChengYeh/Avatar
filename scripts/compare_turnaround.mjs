#!/usr/bin/env node
import { readFile, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { parseArgs } from 'node:util';
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import sharp from 'sharp';

const photoSize = 2048;
const renderSize = 920;
const fullViews = [
    ['01_000deg_front', 'Front (0°)'],
    ['03_090deg_left', 'Left (90°)'],
    ['05_180deg_back', 'Back (180°)'],
];
const earViews = [
    ['head_090deg', 'Left (90°)'],
    ['head_135deg', 'Rear left (135°)'],
    ['head_270deg', 'Right (270°)'],
    ['head_225deg', 'Rear right (225°)'],
];

// Three.js loads the GLB and computes skinned vertices and the camera projection.
// Decode embedded JPEG/PNG textures with Sharp for use by the software rasterizer.
globalThis.self ??= globalThis;
globalThis.createImageBitmap ??= async blob => {
    const { data, info } = await sharp(Buffer.from(await blob.arrayBuffer()))
        .toColourspace('srgb').removeAlpha().raw().toBuffer({ resolveWithObject: true });
    return { data, width: info.width, height: info.height };
};

async function loadModel(path) {
    const glb = await readFile(path);
    const { scene } = await new GLTFLoader().parseAsync(
        glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength), '');
    scene.updateMatrixWorld(true);
    for (const side of ['Left', 'Right']) {
        const shoulder = scene.getObjectByName(side + 'Arm');
        const hand = scene.getObjectByName(side + 'Hand');
        if (!shoulder || !hand) throw new Error(path + ': missing arm bones');
        const offset = hand.getWorldPosition(new THREE.Vector3())
            .sub(shoulder.getWorldPosition(new THREE.Vector3()));
        if (Math.abs(offset.y) > .035 || offset.x * (side === 'Left' ? 1 : -1) < .3) {
            throw new Error(path + ': expected the authored T-pose with Left on +X');
        }
    }
    const meshes = [];
    scene.traverse(mesh => {
        if (!mesh.isSkinnedMesh) return;
        const texture = mesh.material.map;
        const { index, attributes } = mesh.geometry;
        if (!mesh.material.isMeshBasicMaterial || !texture?.image?.data ||
            texture.flipY || !index || !attributes.uv) {
            throw new Error(path + ': expected indexed skinned meshes with unlit glTF textures');
        }
        const world = Array.from({ length: attributes.position.count }, (_, i) =>
            mesh.getVertexPosition(i, new THREE.Vector3()).applyMatrix4(mesh.matrixWorld));
        meshes.push({ world, uv: attributes.uv, index: index.array, image: texture.image,
            cull: mesh.material.side === THREE.FrontSide });
    });
    if (!meshes.length) throw new Error(path + ': no skinned meshes');
    return meshes;
}

function sourceCamera({ phi, th, s, cu, cv, D }) {
    if (D || ![phi, th, s, cu, cv].every(Number.isFinite) || s <= 0) {
        throw new Error('Expected a calibrated orthographic camera');
    }
    const p = THREE.MathUtils.degToRad(phi);
    const t = THREE.MathUtils.degToRad(th);
    const right = new THREE.Vector3(Math.cos(p), 0, -Math.sin(p));
    const up = new THREE.Vector3(-Math.sin(t)*Math.sin(p), Math.cos(t), -Math.sin(t)*Math.cos(p));
    const forward = new THREE.Vector3(Math.sin(p)*Math.cos(t), Math.sin(t), Math.cos(p)*Math.cos(t));
    const camera = new THREE.OrthographicCamera(-cu/s, (photoSize-cu)/s, cv/s, (cv-photoSize)/s, .1, 10);
    camera.position.copy(forward).multiplyScalar(5);
    camera.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(right, up, forward));
    camera.updateMatrixWorld(true);
    return camera;
}

function edge(ax, ay, bx, by, x, y) {
    return (bx - ax)*(y - ay) - (by - ay)*(x - ax);
}

function texturePixel(output, pixel, image, u, v) {
    const { data, width, height } = image;
    const x = THREE.MathUtils.clamp(u*width-.5, 0, width-1);
    const y = THREE.MathUtils.clamp(v*height-.5, 0, height-1);
    const x0 = Math.floor(x), x1 = Math.min(x0+1,width-1), tx = x-x0;
    const y0 = Math.floor(y), y1 = Math.min(y0+1,height-1), ty = y-y0;
    for (let channel = 0; channel < 3; channel++) {
        const a = data[(y0*width+x0)*3+channel]*(1-tx) + data[(y0*width+x1)*3+channel]*tx;
        const b = data[(y1*width+x0)*3+channel]*(1-tx) + data[(y1*width+x1)*3+channel]*tx;
        output[pixel*3+channel] = Math.round(a*(1-ty) + b*ty);
    }
}

function render(meshes, camera) {
    const n = renderSize;
    const rgb = Buffer.alloc(n*n*3, Buffer.from([233,237,232]));
    const depth = new Float32Array(n*n).fill(Infinity);
    const point = new THREE.Vector3();
    for (const { world, uv, index, image, cull } of meshes) {
        const screen = new Float32Array(world.length*3);
        world.forEach((v,i) => {
            point.copy(v).project(camera);
            screen.set([(1+point.x)*n/2, (1-point.y)*n/2, point.z],i*3);
        });
        for (let i = 0; i < index.length; i += 3) {
            const a=index[i], b=index[i+1], c=index[i+2];
            const ax=screen[3*a], ay=screen[3*a+1], bx=screen[3*b], by=screen[3*b+1], cx=screen[3*c], cy=screen[3*c+1];
            const area=edge(ax,ay,bx,by,cx,cy);
            if (Math.abs(area)<1e-8 || (cull && area>=0)) continue;
            const minX=Math.max(0,Math.floor(Math.min(ax,bx,cx))), maxX=Math.min(n-1,Math.ceil(Math.max(ax,bx,cx)));
            const minY=Math.max(0,Math.floor(Math.min(ay,by,cy))), maxY=Math.min(n-1,Math.ceil(Math.max(ay,by,cy)));
            for (let y=minY; y<=maxY; y++) for (let x=minX; x<=maxX; x++) {
                const wa=edge(bx,by,cx,cy,x+.5,y+.5)/area;
                const wb=edge(cx,cy,ax,ay,x+.5,y+.5)/area;
                const wc=1-wa-wb;
                if (Math.min(wa,wb,wc)<-.000001) continue;
                const z=wa*screen[3*a+2]+wb*screen[3*b+2]+wc*screen[3*c+2];
                const pixel=y*n+x;
                if (z>=depth[pixel]) continue;
                depth[pixel]=z;
                texturePixel(rgb,pixel,image,wa*uv.getX(a)+wb*uv.getX(b)+wc*uv.getX(c),
                    wa*uv.getY(a)+wb*uv.getY(b)+wc*uv.getY(c));
            }
        }
    }
    if (!depth.some(Number.isFinite)) throw new Error('No visible model in the calibrated camera');
    return sharp(rgb,{raw:{width:n,height:n,channels:3}});
}

const escapeXml = text => text.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const label = (value,x,y,size,color='#20312b') =>
    '<text x="'+x+'" y="'+y+'" font-size="'+size+'" fill="'+color+'">'+escapeXml(value)+'</text>';

async function makeSheet({ views, models, title, crop, tile, filename, options, cameras }) {
    const [tileWidth,tileHeight] = tile;
    const [x0,y0,x1,y1] = crop;
    const margin = 30, gap = 16, top = 113, rowHeight = tileHeight + 32;
    const width = 2*margin+views.length*tileWidth+(views.length-1)*gap;
    const height = top+(models.length+1)*rowHeight+margin;
    const tags = [label(title,margin,42,28),
        label('Source T-pose · calibrated cameras · fixed crop per view',margin,72,17,'#475a52')];
    const overlays = [];
    for (const [i,[name,heading]] of views.entries()) {
        const left = margin+i*(tileWidth+gap);
        const photo = sharp(join(options.photos,name+'.jpg'));
        const info = await photo.metadata();
        if (info.width !== photoSize || info.height !== photoSize) throw new Error(name+': expected 2048×2048 source');
        const settings = cameras[name];
        if (!settings) throw new Error(name+': missing camera calibration');
        const camera = sourceCamera(settings);
        tags.push(label(heading,left,100,19));
        for (const [j,model] of [null,...models].entries()) {
            const topOfRow = top+j*rowHeight;
            const scale = model ? renderSize/photoSize : 1;
            const cropLeft = Math.round(x0*scale), cropTop = Math.round(y0*scale);
            const img = model ? render(model.meshes,camera) : photo;
            const input = await img.extract({left:cropLeft,top:cropTop,
                width:Math.round(x1*scale)-cropLeft,height:Math.round(y1*scale)-cropTop})
                .resize(tileWidth,tileHeight,{fit:'fill'}).png().toBuffer();
            tags.push(label(model?.label ?? 'Source',left,topOfRow+19,16,'#475a52'));
            overlays.push({input,left,top:topOfRow+27});
        }
    }
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="'+width+'" height="'+height+
        '" font-family="sans-serif">'+tags.join('')+'</svg>';
    await sharp({create:{width,height,channels:3,background:'#f3f4f1'}})
        .composite([...overlays,{input:Buffer.from(svg)}]).png().toFile(join(options.out,filename));
}

const { values: options } = parseArgs({ options:{
    photos:{type:'string'}, cameras:{type:'string'}, model:{type:'string'},
    before:{type:'string'}, out:{type:'string'}, 'ear-crop':{type:'string'}, help:{type:'boolean'},
}});
if (options.help) {
    console.log('node scripts/compare_turnaround.mjs --photos ./photos --cameras ./output/work/cams33.json --model ./output/body_rigged.glb [--before ./previous.glb] [--ear-crop x0,y0,x1,y1] --out ./comparison');
} else {
    for (const key of ['photos','cameras','model','out']) {
        if (!options[key]) throw new Error('Missing --'+key+' (see --help)');
    }
    const earCrop = (options['ear-crop'] ?? '320,100,1750,1295').split(',').map(Number);
    const [left, top, right, bottom] = earCrop;
    if (earCrop.length !== 4 || !earCrop.every(Number.isInteger) ||
        left < 0 || top < 0 || right > photoSize || bottom > photoSize ||
        right-left < 16 || bottom-top < 16) {
        throw new Error('--ear-crop must be x0,y0,x1,y1 within the 2048 px source frame');
    }
    const cameras = JSON.parse(await readFile(options.cameras,'utf8'));
    const models = [];
    if (options.before) models.push({label:'Before',meshes:await loadModel(options.before)});
    models.push({label:options.before?'After':'Model',meshes:await loadModel(options.model)});
    await mkdir(options.out,{recursive:true});
    await makeSheet({views:fullViews,models,title:'Full-body turnaround',crop:[15,30,2033,2030],
        tile:[410,407],filename:'full-comparison.png',options,cameras});
    await makeSheet({views:earViews,models,title:'Ear comparison',crop:earCrop,
        tile:[306,256],filename:'ear-comparison.png',options,cameras});
}
