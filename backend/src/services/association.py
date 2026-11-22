from collections import Counter
from itertools import combinations

def apriori(transactions, min_support=0.08, min_confidence=0.25):
    """Compute frequent itemsets and pair rules from basket family transactions."""
    n = len(transactions)
    if not n:
        return []
    support_count = Counter(item for basket in transactions for item in basket)
    frequent = {frozenset([item]): count / n for item, count in support_count.items() if count / n >= min_support}
    all_frequent = dict(frequent)
    k = 2
    prev = set(frequent)
    while prev:
        candidates = {frozenset(items) for left in prev for right in prev for items in [left | right] if len(items) == k}
        next_level = {}
        for candidate in candidates:
            count = sum(candidate.issubset(basket) for basket in transactions)
            support = count / n
            if support >= min_support:
                next_level[candidate] = support
        all_frequent.update(next_level)
        prev = set(next_level)
        k += 1
    rules = []
    item_support = all_frequent
    for itemset, sup in all_frequent.items():
        if len(itemset) < 2: continue
        for size in range(1, len(itemset)):
            for antecedent_tuple in combinations(itemset, size):
                antecedent = frozenset(antecedent_tuple)
                consequent = itemset - antecedent
                a_sup = item_support.get(antecedent, 0)
                c_sup = item_support.get(consequent, 0)
                if not a_sup or not c_sup: continue
                confidence = sup / a_sup
                lift = confidence / c_sup
                if confidence >= min_confidence:
                    rules.append({"antecedent": sorted(antecedent), "consequent": sorted(consequent), "support": round(sup, 4), "confidence": round(confidence, 4), "lift": round(lift, 4)})
    return sorted(rules, key=lambda r: (r["lift"], r["confidence"]), reverse=True)
