export function less(a: number, b: number) {
  return a < b;
}

/**
 * Return an index k such that
 * seq[i] <= x for i < k and seq[i] > x for i >= k.
 */
export function bisectRight<T, K>(
  seq: T[],
  x: K,
  key: (elem: T) => K,
  cmp: (a: K, b: K) => boolean
): number {
  let lo = 0;
  let hi = seq.length;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (cmp(x, key(seq[mid]))) {
      hi = mid;
    } else {
      lo = mid + 1;
    }
  }
  return lo;
}

export const findGreaterThan = bisectRight;

export function findLessOrEqual<T, K>(
  seq: T[],
  x: K,
  key: (elem: T) => K,
  cmp: (a: K, b: K) => boolean
) {
  return bisectRight(seq, x, key, cmp) - 1;
}

const ROWS_PER_BEAT = 48;

export function beatToRowUnrounded(beat: number): number {
  return beat * ROWS_PER_BEAT;
}

export function beatToRow(beat: number): number {
  return Math.round(beat * ROWS_PER_BEAT);
}

export function rowToBeat(row: number): number {
  return row / ROWS_PER_BEAT;
}

export function rowsToTime(rows: number, bpm: number): number {
  return (rowToBeat(rows) * 60) / bpm;
}
