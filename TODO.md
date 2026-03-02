# 📝 Project TODOs – CamelMedAgents-RAG

This file tracks pending tasks, improvements, and research experiments.

<!-- ---

## 🔥 High Priority

- [ ] Improve intent separation prompt robustness
- [ ] Add evaluation metrics for retrieval performance
- [ ] Add hallucination detection layer
- [ ] Optimize hybrid (dense + sparse) retrieval weighting

---

## 🧠 Query Formulation Pipeline

- [ ] Improve symptom normalization
- [ ] Add severity & duration extraction improvements
- [ ] Add negation detection (e.g., "no chest pain")
- [ ] Benchmark query reformulation vs raw query retrieval

---

## 📚 Retrieval & Vector DB

- [ ] Tune embedding model
- [ ] Add reranker stage
- [ ] Evaluate different chunk sizes
- [ ] Add metadata filtering (age, gender, condition)

---

## 🧪 Evaluation

- [ ] Create test query dataset
- [ ] Measure Precision@K
- [ ] Measure Recall@K
- [ ] Compare hybrid vs dense-only

---

## 🚀 Future Improvements

- [ ] Add medical knowledge graph integration
- [ ] Add feedback learning loop
- [ ] Add UI for query visualization -->

## Query Formulation Pipeline
- [X] Intent Saperator
- [X] Symptom Extractor
- [X] Structure Builder
- [X] Query Generator

---

## Scraping
- [X] Finalizing Data Sources
  - [ ] **Scrapping Strategy**
    - [ ]  **🔎 Step 1 — Understand Your Dataset First (Before Scraping)**
      - [X] **1️⃣ Analyze Label Distribution**
        - [X] Count frequency of each Label
        - [X] Group disease into categories
      - [ ] **2️⃣ Extract Medical Signal from Discussion Column**
          Extract:
        - [ ] Symptoms
        - [ ] Duration
        - [ ] Severity
        - [ ] Triggers
        - [ ] Demographics (age, gender)
     - [ ]  **🧠 Step 2 — What Exactly Should You Scrape?**
       - [ ]  **A) Condition-Level Knowledge**
          This is structured medical grounding (from PubMed + Patient.info).
         - [ ]  Definition
         - [ ]  Causes
         - [ ]  Symptoms
         - [ ]  Diagnosis
         - [ ]  Treatment
         - [ ]  Complications
         - [ ]  When to see doctor
       - [ ] **B) Symptom-Level Knowledge**
       - [ ] **C) Discussion-Level Knowledge (Forums)**
         Scrape threads that:
         **1.** Mention the disease label 
         **2.** OR mention extracted symptoms
         **3.** OR contain similar embedding to your Discussion rows
         - [ ] HealthBoards
         - [ ] Health Shared
         - [ ] Social Health Network
    - [ ] **🧩 Step 3 — Efficient Filtering Strategy**
      - [ ] **Phase 1: Build Disease Target List.** Only scrape content relevant to those diseases.
      - [ ] **Phase 2: Build Symptom Vocabulary.** Run symptom extraction over all Discussion rows. Collect top and  200–500 most frequent normalized symptoms. This becomes secondary scraping keyword list.
      - [ ] **Phase 3: Scraping Strategy Per Source.** 
        - [ ] **🟢 PubMed**
          Focus on below will summarize evidence and less noisy than case reports:
            - [ ] Review articles
            - [ ] Clinical guidelines
            - [ ] Systematic reviews
        - [ ] **🟢 Patient Info**
          Scrape:
             - [ ] Condition pages matching your Label list i.e `/acne`, `/chest-pain`, `/fatigue`
             - [ ] Symptom-based pages matching extracted symptoms
          Do NOT scrape blogs and lifestyle pages.
        - [ ] **🟢 HealthBoards / Health Shared / Social Health Network**
          Instead of scraping full forum, Search internal forum search. For example `acne`, `acne treatment`, `acne scars`
          Scrape:
          - [ ] Thread title
          - [ ] Original post
          - [ ] Accepted/best replies
          - [ ] Highly upvoted replies
          **Ignore:**
          1. One-line replies
          2. Off-topic comments

    - [ ] **🎯 Step 4 — Matching Strategy (Very Important)** 
      Use three layer matching:
        - [ ] Label Matching
        - [ ] Symptom Matching
        - [ ] Embedding Similarity
  - [ ] **Scraping Sources**
    - [ ] PubMed 
    - [ ] Patient Info
    - [ ] HealthBoards
    - [ ] HealthShared
    - [ ] SocialHealthNetwork

---