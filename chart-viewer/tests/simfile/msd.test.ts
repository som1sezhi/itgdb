import { expect, test } from "vitest";
import { parseMSD } from "../../src/simfile/msd";

test("basic MSD parsing", () => {
  const input = `#TAG1:value;
# tag2 : value1:Value2 ;
#TAG3:;#TAG4;
#;`;
  expect(parseMSD(input)).toEqual([
    ["TAG1", "value"],
    [" tag2 ", " value1", "Value2 "],
    ["TAG3", ""],
    ["TAG4"],
    [""],
  ]);
});

test("ignore comments", () => {
  const input = `// comment #FAKETAG:ignore;
#TAG1:value;// comment after value #FAKETAG:ignore;
// comment between values
#TAG2: // comment inside param
line1 // comment inside param; #FAKETAG:ignore;
line2;
#// comment after hash
TAG3:value3;
// comment`;
  expect(parseMSD(input)).toEqual([
    ["TAG1", "value"],
    ["TAG2", " \nline1 \nline2"],
    ["\nTAG3", "value3"],
  ]);
});

test("ignore data outside an MSD value", () => {
  const input = `ignore this#TAG1:value1; ignore
ignorethis #TAG2:value2;
ignore;`;
  expect(parseMSD(input)).toEqual([
    ["TAG1", "value1"],
    ["TAG2", "value2"],
  ]);
});

test("handle escaped characters properly", () => {
  const input = `#TAG1:\\#\\abc\\:def:hi\\;there;
useless data outside a value\\#IGNORE;
useless data outside a value\\\\#TAG2:\\\\:value;`;
  expect(parseMSD(input)).toEqual([
    ["TAG1", "#abc:def", "hi;there"],
    ["TAG2", "\\", "value"],
  ]);
});

test("handle improperly terminated values", () => {
  const input = `#TAG1:value1 \r
\r\t  \t #TAG2:value2;
#TAG3:value3#STILLTHESAMEPARAM
#TAG4:value4 \r
\r\t  \t a #STILLTHESAMEPARAM:
#TAG5:unterminated end`;
  expect(parseMSD(input)).toEqual([
    ["TAG1", "value1"],
    ["TAG2", "value2"],
    ["TAG3", "value3#STILLTHESAMEPARAM"],
    ["TAG4", "value4 \r\n\r\t  \t a #STILLTHESAMEPARAM", ""],
    ["TAG5", "unterminated end"],
  ]);
});
