/**
 * Return an index k such that
 * seq[i] <= x for i < k and seq[i] > x for i >= k.
 */
export function bisectRight<T>(seq: T[], x: number, key: (elem: T) => number) {
  let lo = 0;
  let hi = seq.length;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (x < key(seq[mid])) {
      hi = mid;
    } else {
      lo = mid + 1;
    }
  }
  return lo;
}

export const findGreaterThan = bisectRight;
