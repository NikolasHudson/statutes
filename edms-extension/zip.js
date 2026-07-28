// Hudson EDMSpro minimal ZIP builder — STORE method only (no compression). PDFs
// compress poorly enough that compression isn't worth a ~30KB DEFLATE dep.
// Exposes window.EdmsZip.build(files) → Blob, where files is
// [{ name: string, data: Uint8Array }].

(function () {
  if (window.EdmsZip) return;

  const CRC_TABLE = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) {
        c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      }
      t[n] = c;
    }
    return t;
  })();

  function crc32(bytes) {
    let c = 0xffffffff;
    for (let i = 0; i < bytes.length; i++) {
      c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
    }
    return (c ^ 0xffffffff) >>> 0;
  }

  function dosTime(d) {
    return (
      ((d.getHours() & 0x1f) << 11) |
      ((d.getMinutes() & 0x3f) << 5) |
      Math.floor(d.getSeconds() / 2) & 0x1f
    );
  }

  function dosDate(d) {
    return (
      (((d.getFullYear() - 1980) & 0x7f) << 9) |
      (((d.getMonth() + 1) & 0xf) << 5) |
      (d.getDate() & 0x1f)
    );
  }

  function build(files) {
    const encoder = new TextEncoder();
    const now = new Date();
    const time = dosTime(now);
    const date = dosDate(now);

    const entries = files.map((f) => {
      const nameBytes = encoder.encode(f.name);
      const data = f.data instanceof Uint8Array ? f.data : new Uint8Array(f.data);
      return { nameBytes, data, crc: crc32(data), time, date };
    });

    let total = 22; // End-of-central-directory record
    for (const e of entries) {
      total += 30 + e.nameBytes.length + e.data.length; // LFH + name + data
      total += 46 + e.nameBytes.length; // CD entry
    }

    const buf = new ArrayBuffer(total);
    const view = new DataView(buf);
    const u8 = new Uint8Array(buf);
    let offset = 0;
    const w16 = (v) => {
      view.setUint16(offset, v, true);
      offset += 2;
    };
    const w32 = (v) => {
      view.setUint32(offset, v >>> 0, true);
      offset += 4;
    };
    const wBytes = (b) => {
      u8.set(b, offset);
      offset += b.length;
    };

    const cdRecords = [];

    for (const e of entries) {
      const lfhOffset = offset;
      w32(0x04034b50); // local file header signature
      w16(20); // version needed
      w16(0); // general purpose flags
      w16(0); // compression: STORE
      w16(e.time);
      w16(e.date);
      w32(e.crc);
      w32(e.data.length); // compressed
      w32(e.data.length); // uncompressed
      w16(e.nameBytes.length);
      w16(0); // extra field length
      wBytes(e.nameBytes);
      wBytes(e.data);
      cdRecords.push({ ...e, lfhOffset });
    }

    const cdStart = offset;
    for (const e of cdRecords) {
      w32(0x02014b50); // central directory header signature
      w16(20); // version made by
      w16(20); // version needed
      w16(0); // flags
      w16(0); // method
      w16(e.time);
      w16(e.date);
      w32(e.crc);
      w32(e.data.length);
      w32(e.data.length);
      w16(e.nameBytes.length);
      w16(0); // extra
      w16(0); // comment length
      w16(0); // disk number
      w16(0); // internal attrs
      w32(0); // external attrs
      w32(e.lfhOffset);
      wBytes(e.nameBytes);
    }
    const cdSize = offset - cdStart;

    w32(0x06054b50); // end of central directory signature
    w16(0); // disk
    w16(0); // disk where CD starts
    w16(entries.length); // entries on this disk
    w16(entries.length); // total entries
    w32(cdSize);
    w32(cdStart);
    w16(0); // comment length

    return new Blob([u8], { type: "application/zip" });
  }

  window.EdmsZip = { build };
})();
