# **Asset Intelligence Graph-RAG for Smart Manufacturing**

This project implements a **full digital thread intelligence system** combining:

* **Neo4j knowledge graph** (assemblies → parts → specs → embeddings)
* **Hybrid RAG retrieval engine**
* **Graph-aware LLM reasoning**
* **Compatibility scoring model for mechanical components**
* **FastAPI backend**
* **React frontend**
* **YAML ingestion + document storage**

It supports **natural-language engineering queries**, **part replacement suggestions**, **compatibility evaluation**, and **intelligent search** across manufacturing assemblies.

This is essentially a **mini industrial PLM + RAG + graph** system.

---

# **Data Model — The Digital Thread Knowledge Graph**

### 1. **Product Layer**

* Each product is a digital entity in Neo4j.
* Stores:

  * Name, SKU, description
  * Embedding (for product-level semantic retrieval)

Example:
**Industrial Lathe Machine**

---

### 2. **Assembly Layer**

Automatically generated from part categories using an `ASSEMBLY_MAP`, e.g.:

* **Spindle Assembly**
* **Z Axis Assembly**
* **X Axis Assembly**
* **Tailstock Assembly**
* **Mold System Assembly**
* **Electronics Assembly**

Assemblies are shared across parts and products.

Graph structure:

```
(Product) —[:HAS_ASSEMBLY]→ (Assembly) —[:HAS_PART]→ (Part)
```

---

### 3. **Parts**

Each part stores:

* `part_id`, `name`, `category`, `description`
* **Embedding (384-D)** using gte-small
* **Specs** (thread size, diameter, pitch, torque, etc.)
* **Children** for hierarchical structure (subcomponents)

Graph:

```
(Part) —[:HAS_CHILD]→ (Part)
(Part) —[:HAS_SPEC]→ (Spec)
```

---

### 4. **Specs (Node-Key Unique)**

Specs are stored as:

```
(key, value, unit)
```

With uniqueness enforced via a **NODE KEY constraint**.

This allows powerful spec-level queries like:

```
MATCH (p:Part)-[:HAS_SPEC]->(s:Spec {key:"pitch", value:5})
```

---

# **Ingestion Pipeline**

### YAML Ingestion

User uploads a YAML file:

```
product:
  name: Industrial Lathe Machine
  description: ...

parts:
  - part_id: SPINDLE-MT5-38HOLE
    category: Spindle
    specs:
      - key: "thread"
        value: "M45"
```

The ingestor:

1. Creates/updates product
2. Creates assemblies
3. Creates part nodes
4. Embeds each part's name + description
5. Stores specs (forcing non-null units)
6. Builds parent-child relationships recursively

This yields a **consistent, hierarchical digital twin**.

---

# **Retrieval Engine (Graph-RAG)**

This is one of the most advanced parts of the system.

## **Step 1: Embed the user question**

Using the same 384-D embedding model as parts.

---

## **Step 2: Perform Hybrid Retrieval**

Two searches run in parallel:

### **A. Vector semantic search**

```
CALL db.index.vector.queryNodes(
  'part_embedding_index',
  $k,
  $embedding
)
```

Retrieves semantically relevant parts even if keywords are missing.

---

### **B. Full-text search**

```
CALL db.index.fulltext.queryNodes(
  'part_fulltext_idx',
  $query
)
```

Retrieves keyword matches with fuzzy ranking.

---

## **Step 3: Filter by product or assembly**

We enforce digital-thread scoping:

* Only show parts that belong to the selected product
* Or selected assembly

---

## **Step 4: Merge and re-rank results**

We combine vector + keyword results, keeping only the **highest score per part_id**.

---

## **Step 5: Enrich results**

We fetch:

* Specs
* Product associations
* Assembly placement

---

## **Step 6: Fetch mutual compatibility edges**

If retrieved parts are known compatible, we display:

```
A ↔ B: score 0.73 — pitch matches; same assembly; compatible torque range
```

---

## **Step 7: LLM answer synthesis**

The LLM receives:

* Top retrieved parts
* Graph structure
* Specs
* Compatibility edges

It generates a structured, human-like engineering answer.

---

# ⚙️ **Compatibility Scoring Model — Why It’s Unique**

The compatibility model compares two parts (existing vs existing, or new vs existing) along **four dimensions**, each independently computed:

---

## **1. Mechanical Similarity (0–1)**

Checks:

* diameters
* lengths
* pitches
* threads
* torque ratings
* fits and tolerances

Scoring formula:

```
mechanical_score = weighted match of overlapping mechanical specs
```

---

## **2. Functional Similarity (0–1)**

Checks:

* part category
* assembly role
* operational purpose
* motion profile
* intended load path

E.g., two ballscrews functionally similar even if dimensions differ.

---

## **3. Semantic Similarity (0–1)**

Embedding distance between part descriptions.

This is extremely useful when specs are missing.

---

## **4. Hierarchical Similarity (0–1)**

Checks:

* Are both parts in the same assembly?
* Same subassembly?
* Do they share a parent/child?

Example:

```
Spindle Nut ↔ Spindle Shaft → HIGH
Ballscrew ↔ Tailstock → LOW
```

---

## **Final Score**

```
final_score = (0.35 * mechanical)
            + (0.25 * functional)
            + (0.25 * semantic)
            + (0.15 * hierarchy)
```

We also store:

```
explanations: ["same pitch", "same spindle assembly", ...]
```

---

# **New Part Compatibility**

When checking a **new, never-before-seen part**:

1. LLM extracts structured specs from text
2. Embedding for semantic comparison
3. Filtering by product assemblies
4. Compute compatibility score against all known parts
5. Return ranked results + explanations

This is a **digital twin–aware engineering recommender system**.

No PLM today does this.

---

# **FastAPI Backend**

API routes include:

* `/api/query` → RAG reasoning
* `/api/compat/product/{name}` → existing compatibility
* `/api/compat/new-part` → new part scoring
* `/api/upload/doc` → store BOMs/pdfs/images
* `/api/upload/yaml` → ingest new products
* `/api/stt` → Groq Whisper speech-to-text

Simple, clean, industry-ready.

---

# **React Frontend**

Key features:

* Dark text + white background “ERP style” UI
* RAG Query Mode
* Existing Compatibility Mode
* New Part Compatibility Mode
* Upload Documents
* YAML ingestion
* Download Markdown report

---

# *Why this project is one-of-a-kind for Smart Manufacturing:*

## **1. Combines PLM data + RAG + Graph Intelligence**

Manufacturing data is usually siloed in:

* PLM
* MES
* ERP
* Excel BOMs
* Vendor PDFs

This system unifies them into a **searchable digital thread**.

---

## **2. Compatible with real factory workflows**

Engineers frequently ask:

* “What part should I replace this with?”
* “Are these two components interchangeable?”
* “What does this assembly contain?”

No existing search engine can answer these without manual lookup.

This system can.

---

## **3. True engineering retrieval**

Most RAG systems are text-only.
This system uses:

### ✔ Graph context

✔ Specs
✔ Assemblies
✔ Vector embeddings
✔ Hierarchical similarity
✔ Multi-factor compatibility

This yields **far more accurate engineering answers**.

---

## **4. Novel compatibility scoring hybrid**

No manufacturing platform (PTC Windchill, Siemens Teamcenter, Dassault 3DEXPERIENCE) currently offers:

* ML-driven compatibility
* Assembly-aware matching
* LLM-based explanation of engineering alternatives

This system does.

---

## **5. Extensible digital thread**

Adding new machines/products is as easy as uploading a YAML file.

This makes it infinitely scalable across:

* entire factories
* robotics systems
* CNC fleets
* automotive component trees

---
