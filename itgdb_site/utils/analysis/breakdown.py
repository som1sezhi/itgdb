"""Routines for generating stream breakdown strings from the results
of ChartAnalyzer.get_stream_info()."""

import math

MAX_BREAKDOWN_SEGMENTS = 24


# specify all runs, and all breaks longer than 1 measure
def _gen_full_breakdown(stream_info):
    segs = stream_info['segments']
    if len(segs) > MAX_BREAKDOWN_SEGMENTS:
        return None
    
    multiplier = stream_info['quant'] / 16
    breakdown_parts = []
    for seg in segs:
        seg_len = math.floor(abs(seg) * multiplier)
        if seg > 0: # if this is a stream segment
            breakdown_parts.append(str(seg_len))
        else: # if this is a break
            breakdown_parts.append(f'({seg_len})')
    
    return ' '.join(breakdown_parts)


# represent breaks with symbols:
# - "'": 1 measure
# - '-': 2-4 measures
# - '/': 5-31 measures
# - '|': >=32 measures
# simplification levels:
# - 1: turn all breaks into symbols
# - 2: breaks of 1 measure are accumulated into broken stream
# - 3: all '-' breaks are accumulated into broken stream
def _gen_simplified_breakdown(stream_info, simplify_level):
    segs = stream_info['segments']
    multiplier = stream_info['quant'] / 16

    breakdown_parts = []
    accum_stream = 0 # measured in original chart measures
    is_broken = False

    def add_part(adj_break_len=None):
        nonlocal accum_stream, is_broken
        part = str(math.floor(accum_stream * multiplier))
        if is_broken:
            part += '*'
        if adj_break_len is not None:
            if adj_break_len < 2:
                part += "'"
            elif adj_break_len < 5:
                part += '-'
            elif adj_break_len < 32:
                part += '/'
            else:
                part += ' | '
        breakdown_parts.append(part)
        # reset
        accum_stream = 0
        is_broken = False
    
    for i, seg in enumerate(segs):
        # NOTE: we will always append one more breakdown part after this loop,
        # so if at any point during this loop does the length of breakdown_parts
        # reach the maximum, it will break the maximum once it leaves the loop.
        # thus we should abort now.
        if len(breakdown_parts) >= MAX_BREAKDOWN_SEGMENTS:
            return None

        if seg > 0: # if stream
            # if previous segment was also stream, this indicates a 
            # 1-measure break
            if i > 0 and segs[i - 1] > 0:
                if simplify_level == 1:
                    # notate the 1-measure break
                    # note: 1 measure break * multiplier = multiplier
                    add_part(multiplier)
                else:
                    # accumulate break into broken stream
                    accum_stream += 1
                    is_broken = True
                
            # add the current stream segment
            accum_stream += seg

        else: # if break
            break_len = -seg
            adj_break_len = break_len * multiplier

            # if the break is short enough, merge it into the previous
            # stream segment instead of ending the stream segment
            if simplify_level == 3 and adj_break_len < 5:
                accum_stream += break_len
                is_broken = True
            else:
                add_part(adj_break_len)
    
    # ensure we do not break the maximum by adding one more segment
    if len(breakdown_parts) == MAX_BREAKDOWN_SEGMENTS:
        return None
    # add remaining stream
    add_part()

    return ''.join(breakdown_parts)


def generate_breakdown(stream_info: dict) -> str:
    if stream_info['segments']:
        # attempt to generate simplier and simplier breakdowns until
        # we get one that fits under the minimum
        bd = _gen_full_breakdown(stream_info)
        if bd is None:
            for simplify_level in range(1, 4):
                bd = _gen_simplified_breakdown(stream_info, simplify_level)
                if bd is not None:
                    break
        if bd is None:
            bd = f'{stream_info["total_stream"]} total'
        
        # add '@ bpm' part if this is not 16th stream
        if stream_info['quant'] != 16:
            bpms = stream_info['bpms']
            multiplier = stream_info['quant'] / 16
            adj_bpms = [
                round(bpms[0] * multiplier),
                round(bpms[1] * multiplier)
            ]
            # display the bpm as 1 number if the bpm bounds round to the
            # same number, or if the bounds are so close (e.g. float
            # imprecision) that they should be considered as the same.
            # the 2nd condition catches some cases that the 1st doesn't, e.g.
            # if the multiplier takes min_bpm and max_bpm to something like
            # 120.49999... and 120.500...01, which will round to different nums
            if adj_bpms[0] == adj_bpms[1] or bpms[1] - bpms[0] < 1e-9:
                bd += f' @ {adj_bpms[1]}'
            else:
                bd += f' @ {adj_bpms[0]}-{adj_bpms[1]}'
    else:
        bd = 'No streams'
    return bd