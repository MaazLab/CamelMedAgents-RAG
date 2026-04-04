# Medical Signal Extraction steps

Instead of one prompt:

Use **multi-stage extraction**.

---

# Stage 1 — Symptom Extraction (MOST IMPORTANT)

Prompt only does:

```
extract symptoms
extract locations
extract severity
```

Example schema:

```
{
  "symptoms":[
     {
       "name":"",
       "normalized_name":"",
       "location":"",
       "severity":""
     }
  ]
}
```

This stage must be **extremely accurate**.

---

# Stage 2 — Temporal Information

Extract:

```
duration
frequency
onset
```

---

# Stage 3 — Patient Context

Extract:

```
age
gender
pregnancy
comorbidities
```

---

# Stage 4 — Clinical Interpretation

Extract:

```
intent
red_flag
query_complexity
```

This stage uses outputs of stage 1.

---

# Recommended Architecture

```
patient query
      ↓
Stage 1: symptom extraction
      ↓
Stage 2: temporal extraction
      ↓
Stage 3: demographics extraction
      ↓
Stage 4: intent + red flag classification
      ↓
post-processing (compute complexity score)
```

---

# One More Important Insight

Your project is **symptom-driven retrieval**.

So the **most critical extraction is symptoms**.

Everything else is secondary.

Your current prompt treats **symptoms as just one of many tasks**, which weakens it.

---


### Recommendation

Split extraction into **4 smaller prompts**:

1️⃣ Symptom extraction
2️⃣ Temporal extraction
3️⃣ Patient context extraction
4️⃣ Intent + risk classification

This will **dramatically improve symptom quality**.

