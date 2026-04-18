# v44 - Functional First + Source Agnostic Matching

def classify_function(product_name):
    name = product_name.lower()
    if "hydroflam" in name:
        return "fire_moisture"
    if "flam" in name:
        return "fire"
    if "hydro" in name or "h2" in name or "smart h" in name:
        return "moisture"
    return "standard"

def match(product, candidates):
    # 1. restrictions
    candidates = [c for c in candidates if c["unit"] == product["unit"]]

    # 2. functional filter (CRITICAL FIX)
    func = classify_function(product["name"])
    candidates = [c for c in candidates if classify_function(c["name"]) == func]

    # 3. saved comparisons (strongest)
    for c in candidates:
        if c.get("saved_match") == product["name"]:
            return c

    # 4. stable equivalence
    for c in candidates:
        if c.get("equivalence") == product.get("equivalence"):
            return c

    # 5. fallback
    return candidates[0] if candidates else None
