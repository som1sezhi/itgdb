export type MSDParams = string[][];
export type MSDRecord = Record<string, string[]>;

export function parseMSD(data: string): MSDParams {
  // basically a port of the logic from SM's MsdFile::ReadBuf()
  let readingValue = false;
  let pos = 0;
  let processed = "";
  const len = data.length;
  const ret: string[][] = [];

  function addParam() {
    ret[ret.length - 1].push(processed);
  }

  while (pos < len) {
    // skip comments
    if (data.startsWith("//", pos)) {
      do {
        pos++;
      } while (pos < len && data[pos] !== "\r" && data[pos] !== "\n");
      continue;
    }

    // deal with unexpected # while inside a value
    if (readingValue && data[pos] === "#") {
      // ensure the '#' is the first non-' ' or '\t' char in this line
      if (/[\r\n][ \t]*$/.test(processed)) {
        console.log("hello", ret, processed);
        // end the current value (strip out whitespace on the right)
        processed = processed.replace(/[\r\n\t ]+$/, "");
        addParam();
        processed = "";
        readingValue = false;
      } else {
        // if # is not the first non-whitespace char on this line,
        // just read it as normal
        processed += data[pos++];
        continue;
      }
    }

    // start a new value
    if (!readingValue && data[pos] === "#") {
      ret.push([]);
      readingValue = true;
    }

    if (!readingValue) {
      pos += data[pos] === "\\" ? 2 : 1;
      continue; // skip meaningless data outside a value
    }

    // now we can assume readingValue === true

    if (data[pos] === ":" || data[pos] === ";")
      // end the current param
      addParam();

    if (data[pos] === "#" || data[pos] === ":") {
      // begin a new param
      pos++;
      processed = "";
      continue;
    }

    if (data[pos] === ";") {
      // end the current value
      readingValue = false;
      pos++;
      continue;
    }

    if (data[pos] === "\\")
      // escape by forcing the next char to be read normally
      pos++;

    if (pos < len) {
      // read normal character
      processed += data[pos++];
    }
  }

  // add any unterminated value at end
  if (readingValue) addParam();

  return ret;
}
