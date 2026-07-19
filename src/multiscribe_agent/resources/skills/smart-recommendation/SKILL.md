---
name: Smart Recommendation
description: Rank candidate items using persisted user preferences when available.
bins: []
---

# Smart Recommendation

When selecting top candidates, favor preferred tags and recent high-quality items, and exclude blocked sources.
If preference memory is unavailable, use a generic quality and freshness ranking and clearly state that it is degraded.
Return ranked items with a numeric score and concise reasons.
