"""Extract scheme/project names from property titles using Gemini AI.

Processes properties in batches and caches results in data/scheme_cache.json.
Only new/uncached titles are processed on each run.

Requires GEMINI_API_KEY environment variable.
"""

import json
import os
import re
import time

CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "scheme_cache.json")
PROPERTIES_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "properties.json")
BATCH_SIZE = 50  # Titles per API call


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def extract_batch(client, titles):
    """Send a batch of titles to Gemini and get scheme names back."""
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    prompt = f"""Extract the property scheme/project/development name from each Malaysian property listing title below.
The scheme name is the specific residential or commercial development name (e.g. "Bayu Angkasa", "Pelangi Damansara", "Ara Damansara").
Do NOT include generic terms like "Apartment", "Condominium", "House" unless they are part of the proper name.
If no specific scheme name can be identified, output "NONE".

Return ONLY a JSON array of strings, one per title, in the same order. No explanation.

Titles:
{numbered}"""

    response = client.models.generate_content(
        model="gemma-4-31b-it",
        contents=prompt,
    )

    # Parse response
    text = response.text.strip()
    # Remove markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        results = json.loads(text)
        if isinstance(results, list) and len(results) == len(titles):
            return results
    except json.JSONDecodeError:
        pass

    # Fallback: return None for all
    return [None] * len(titles)


def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("  GEMINI_API_KEY not set, skipping scheme extraction")
        return

    from google import genai

    client = genai.Client(api_key=api_key)

    with open(PROPERTIES_FILE, "r") as f:
        properties = json.load(f)

    cache = load_cache()

    # Collect unique titles from active properties that aren't cached
    title_to_addr = {}
    for p in properties.values():
        if p.get("expired"):
            continue
        title = p.get("title", "").strip()
        addr = (p.get("header_full") or "").strip()
        if title and addr and addr not in cache:
            title_to_addr[addr] = title

    uncached = list(title_to_addr.items())
    if not uncached:
        print("  All scheme names already extracted (cache hit)")
        return

    print(f"  Need to extract scheme names for {len(uncached)} properties")

    total_processed = 0
    for batch_start in range(0, len(uncached), BATCH_SIZE):
        batch = uncached[batch_start : batch_start + BATCH_SIZE]
        addrs = [a for a, _ in batch]
        titles = [t for _, t in batch]

        try:
            results = extract_batch(client, titles)
            for addr, scheme in zip(addrs, results):
                if scheme and scheme != "NONE":
                    cache[addr] = scheme
                else:
                    cache[addr] = ""
            total_processed += len(batch)
        except Exception as e:
            print(f"  Error processing batch: {e}")
            for addr in addrs:
                cache[addr] = ""
            total_processed += len(batch)

        if (batch_start + BATCH_SIZE) < len(uncached):
            time.sleep(1)  # Rate limit

        if total_processed % 200 == 0 or batch_start + BATCH_SIZE >= len(uncached):
            print(f"  Progress: {total_processed}/{len(uncached)}")
            save_cache(cache)

    save_cache(cache)
    named = sum(1 for v in cache.values() if v)
    print(f"  Scheme extraction complete: {named} named, {len(cache) - named} unnamed")


if __name__ == "__main__":
    main()
