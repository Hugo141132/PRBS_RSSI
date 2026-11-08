"""Script to evaluate candidate BCH codes across seeds and paths."""
import time
import numpy as np
from pathlib import Path
from rssi_skg.loader import load_rssi_workbook
from rssi_skg.filter import filter_rssi_channels, FilterConfig
from rssi_skg.quantization import quantize_channels, QuantizationConfig
from rssi_skg.prbs import expand_channels_prbs, PRBSConfig
from rssi_skg.reconciliation import (
    DEFAULT_BCH_CODE_2BIT,
    DEFAULT_BCH_CODE_4BIT,
    generate_helper_data,
    evaluate_reconciliation_pair,
    get_bch_code,
)

data_path = Path("data/raw/dummy/Dummy RSSI (data Indoor).xlsx")
raw = load_rssi_workbook(data_path)
filtered = filter_rssi_channels(raw, FilterConfig())
quant = quantize_channels(filtered, QuantizationConfig())
prbs = expand_channels_prbs(quant, PRBSConfig())

path_bitstreams = {
    "quant_2bit": {
        "Alice": quant.bitstreams_2bit["Alice"],
        "Bob": quant.bitstreams_2bit["Bob"],
        "Eve1-Alice": quant.bitstreams_2bit["Eve1-Alice"],
        "Eve1-Bob": quant.bitstreams_2bit["Eve1-Bob"],
    },
    "quant_4bit": {
        "Alice": quant.bitstreams_4bit["Alice"],
        "Bob": quant.bitstreams_4bit["Bob"],
        "Eve1-Alice": quant.bitstreams_4bit["Eve1-Alice"],
        "Eve1-Bob": quant.bitstreams_4bit["Eve1-Bob"],
    },
    "prbs_2bit": {
        ch: prbs.channels[ch].bitstream_2bit for ch in prbs.channels
    },
    "prbs_4bit": {
        ch: prbs.channels[ch].bitstream_4bit for ch in prbs.channels
    },
}

# Warm up get_bch_code
for c in [(127, 1, 62), (255, 9, 63), (255, 1, 103), (511, 1, 198), (1023, 1, 375),
          (31, 1, 13), (63, 1, 24), (127, 1, 36), (255, 9, 62), (255, 1, 64),
          (511, 19, 116), (511, 10, 120), (511, 1, 128),
          (1023, 36, 222), (1023, 26, 224), (1023, 16, 240), (1023, 11, 248), (1023, 1, 256)]:
    get_bch_code(*c)

def evaluate_candidate(family, paths, code, seeds=(42, 100, 2026, 9999)):
    n, k, t = code
    bch = get_bch_code(n, k, t)
    d_val = 2 * t + 1

    results_per_seed = []
    
    t0 = time.perf_counter()
    for seed in seeds:
        rng = np.random.default_rng(seed)
        seed_res = {"seed": seed, "bob_exact": True, "eve_stats": []}
        
        for path_name in paths:
            b_dict = path_bitstreams[path_name]
            helpers, orig_len, pad = generate_helper_data(
                source_bits=b_dict["Alice"],
                n=n,
                k=k,
                t=t,
                rng=rng,
            )
            
            # Bob
            res_ab = evaluate_reconciliation_pair(
                source_bits=b_dict["Alice"],
                receiver_bits=b_dict["Bob"],
                helper_blocks=helpers,
                n=n,
                k=k,
                t=t,
                path_name=path_name,
                pair_name="Alice–Bob",
                source_name="Alice",
                receiver_name="Bob",
                is_legitimate=True,
                padding_count=pad,
                designed_d=d_val,
                interleaving="OFF",
            )
            if not res_ab.exact_recovery or res_ab.post_reconcile_kar < 100.0:
                seed_res["bob_exact"] = False
                
            # Eve1-Alice
            res_ea = evaluate_reconciliation_pair(
                source_bits=b_dict["Alice"],
                receiver_bits=b_dict["Eve1-Alice"],
                helper_blocks=helpers,
                n=n,
                k=k,
                t=t,
                path_name=path_name,
                pair_name="Alice–Eve1-Alice",
                source_name="Alice",
                receiver_name="Eve1-Alice",
                is_legitimate=False,
                padding_count=pad,
                designed_d=d_val,
                interleaving="OFF",
            )
            
            # Eve1-Bob
            res_eb = evaluate_reconciliation_pair(
                source_bits=b_dict["Alice"],
                receiver_bits=b_dict["Eve1-Bob"],
                helper_blocks=helpers,
                n=n,
                k=k,
                t=t,
                path_name=path_name,
                pair_name="Alice–Eve1-Bob",
                source_name="Alice",
                receiver_name="Eve1-Bob",
                is_legitimate=False,
                padding_count=pad,
                designed_d=d_val,
                interleaving="OFF",
            )
            
            for r in [res_ea, res_eb]:
                delta = r.post_reconcile_kar - r.pre_reconcile_kar
                pos_delta = max(0.0, delta)
                seed_res["eve_stats"].append({
                    "path": path_name,
                    "pair": r.pair_name,
                    "pre_kar": r.pre_reconcile_kar,
                    "post_kar": r.post_reconcile_kar,
                    "delta": delta,
                    "pos_delta": pos_delta,
                    "succ": r.success_blocks,
                    "fail": r.detected_failure_blocks,
                    "misc": r.miscorrected_blocks,
                })
        results_per_seed.append(seed_res)
    elapsed = time.perf_counter() - t0
    
    # Check Bob exact across all seeds
    all_bob_exact = all(s["bob_exact"] for s in results_per_seed)
    
    # Calculate overall Eve metrics across all evaluations
    all_pos_deltas = [stat["pos_delta"] for s in results_per_seed for stat in s["eve_stats"]]
    all_deltas = [stat["delta"] for s in results_per_seed for stat in s["eve_stats"]]
    max_pos_delta = max(all_pos_deltas)
    mean_pos_delta = np.mean(all_pos_deltas)
    
    # Helper overhead and parity leakage:
    # helper_bits = num_blocks * n. Parity bits = num_blocks * (n - k).
    total_helper_bits = 0
    total_parity_bits = 0
    for path_name in paths:
        L = len(path_bitstreams[path_name]["Alice"])
        m = (L + n - 1) // n
        total_helper_bits += m * n
        total_parity_bits += m * (n - k)
        
    return {
        "family": family,
        "code": code,
        "all_bob_exact": all_bob_exact,
        "max_pos_delta": max_pos_delta,
        "mean_pos_delta": mean_pos_delta,
        "total_helper_bits": total_helper_bits,
        "total_parity_bits": total_parity_bits,
        "elapsed": elapsed,
        "results_per_seed": results_per_seed,
    }

if __name__ == "__main__":
    candidates_2bit = [
        (127, 1, 62), # Default
        (127, 1, 63),
        (255, 1, 103),
        (511, 1, 198),
        (1023, 1, 375),
    ]
    
    candidates_4bit = [
        (255, 9, 63), # Default
        (255, 9, 62),
        (31, 1, 13),
        (63, 1, 24),
        (127, 1, 36),
        (255, 1, 64),
        (511, 19, 116),
        (511, 10, 120),
        (511, 1, 128),
        (1023, 36, 222),
        (1023, 26, 224),
        (1023, 16, 240),
        (1023, 11, 248),
        (1023, 1, 256),
    ]
    
    print("--- EVALUATING 2-BIT CANDIDATES ---")
    res_2bit = []
    for c in candidates_2bit:
        out = evaluate_candidate("2-bit", ["quant_2bit", "prbs_2bit"], c)
        res_2bit.append(out)
        print(f"Code {c}: Bob={out['all_bob_exact']}, MaxPosDelta={out['max_pos_delta']:.2f}pp, MeanPosDelta={out['mean_pos_delta']:.2f}pp, Helper={out['total_helper_bits']}b, ParityBound={out['total_parity_bits']}b, Time={out['elapsed']:.2f}s")
        # print first seed stats
        s0 = out["results_per_seed"][0]
        for st in s0["eve_stats"]:
            print(f"    [{st['path']}-{st['pair']}] Pre={st['pre_kar']:.2f}%, Post={st['post_kar']:.2f}%, Delta={st['delta']:+.2f}pp, Succ={st['succ']}, Fail={st['fail']}, Misc={st['misc']}")

    print("\n--- EVALUATING 4-BIT CANDIDATES ---")
    res_4bit = []
    for c in candidates_4bit:
        out = evaluate_candidate("4-bit", ["quant_4bit", "prbs_4bit"], c)
        res_4bit.append(out)
        print(f"Code {c}: Bob={out['all_bob_exact']}, MaxPosDelta={out['max_pos_delta']:.2f}pp, MeanPosDelta={out['mean_pos_delta']:.2f}pp, Helper={out['total_helper_bits']}b, ParityBound={out['total_parity_bits']}b, Time={out['elapsed']:.2f}s")
        s0 = out["results_per_seed"][0]
        for st in s0["eve_stats"]:
            print(f"    [{st['path']}-{st['pair']}] Pre={st['pre_kar']:.2f}%, Post={st['post_kar']:.2f}%, Delta={st['delta']:+.2f}pp, Succ={st['succ']}, Fail={st['fail']}, Misc={st['misc']}")

