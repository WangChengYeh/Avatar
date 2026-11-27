/**
 * Avatar 專案總覽 — Google Apps Script web app.
 * Runs as you, reads Drive avatar/<executor>/avatar_NNN/vNNN/*_stageN_*.zip directly (no API key, no sharing needed).
 * Zips are read with HTTP ranges: only the directory and the entries the page asks for.
 */
var ROOT_NAME = 'avatar';

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Avatar 專案總覽')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

function sorted_(it) {
  var a = [];
  while (it.hasNext()) a.push(it.next());
  return a.sort(function (x, y) { return x.getName().localeCompare(y.getName()); });
}

function findRoot_() {
  var it = DriveApp.getFoldersByName(ROOT_NAME);
  while (it.hasNext()) {
    var f = it.next();
    if (f.getFolders().hasNext()) return f;
  }
  throw new Error('Drive 裡找不到有子資料夾的 ' + ROOT_NAME + '/ 資料夾');
}

/** executor / avatar_NNN / vNNN / stage zips */
function getTree() {
  var root = findRoot_(), avatars = [];
  sorted_(root.getFolders()).forEach(function (ex) {
    sorted_(ex.getFolders()).forEach(function (av) {
      if (!/^avatar_/.test(av.getName())) return;
      var versions = [];
      sorted_(av.getFolders()).forEach(function (v) {
        if (!/^v\d+$/.test(v.getName())) return;
        var zips = [], fi = v.getFiles();
        while (fi.hasNext()) {
          var f = fi.next(), n = f.getName();
          if (/_stage\d_.*\.zip$/.test(n))
            zips.push({id: f.getId(), name: n, size: f.getSize(), modifiedTime: f.getLastUpdated().toISOString()});
        }
        versions.push({name: v.getName(), id: v.getId(), zips: zips});
      });
      avatars.push({executor: ex.getName(), avatar: av.getName(), folder: av.getId(), versions: versions});
    });
  });
  return {avatars: avatars, at: new Date().toISOString()};
}

function range_(id, a, b) {
  var r = UrlFetchApp.fetch('https://www.googleapis.com/drive/v3/files/' + encodeURIComponent(id) + '?alt=media&supportsAllDrives=true', {
    headers: {Authorization: 'Bearer ' + ScriptApp.getOAuthToken(), Range: 'bytes=' + a + '-' + b},
    muteHttpExceptions: true
  });
  var code = r.getResponseCode();
  if (code !== 200 && code !== 206) throw new Error('Drive 下載 ' + code + '：' + r.getContentText().slice(0, 200));
  return r.getContent();   // signed bytes
}
function u16_(b, o) { return (b[o] & 255) | ((b[o + 1] & 255) << 8); }
function u32_(b, o) { return ((b[o] & 255) | ((b[o + 1] & 255) << 8) | ((b[o + 2] & 255) << 16)) + (b[o + 3] & 255) * 16777216; }
function str_(b) { return Utilities.newBlob(b).getDataAsString('UTF-8'); }

/**
 * The zip entries whose names match any of `patterns` (regex strings), still compressed:
 * [{name, method (0 stored / 8 deflate), b64}]. The page inflates them.
 */
function readEntries(id, size, patterns) {
  var res = patterns.map(function (p) { return new RegExp(p); });
  var t0 = Math.max(0, size - 65557), tail = range_(id, t0, size - 1), e = tail.length - 22;
  while (e >= 0 && u32_(tail, e) !== 0x06054b50) e--;
  if (e < 0) throw new Error('不是 zip 檔');
  var n = u16_(tail, e + 10), cdSize = u32_(tail, e + 12), cdOff = u32_(tail, e + 16);
  var cd = cdOff >= t0 ? tail.slice(cdOff - t0, cdOff - t0 + cdSize) : range_(id, cdOff, cdOff + cdSize - 1);
  var out = [], p = 0;
  for (var i = 0; i < n; i++) {
    var method = u16_(cd, p + 10), csize = u32_(cd, p + 20), nl = u16_(cd, p + 28), xl = u16_(cd, p + 30), cl = u16_(cd, p + 32),
        lo = u32_(cd, p + 42), name = str_(cd.slice(p + 46, p + 46 + nl));
    p += 46 + nl + xl + cl;
    if (!res.some(function (r) { return r.test(name); })) continue;
    var blk = range_(id, lo, Math.min(size - 1, lo + 30 + nl + xl + csize + 1023));
    var st = 30 + u16_(blk, 26) + u16_(blk, 28);
    if (st + csize > blk.length) blk = range_(id, lo, lo + st + csize - 1);
    out.push({name: name, method: method, b64: Utilities.base64Encode(blk.slice(st, st + csize))});
  }
  return out;
}
