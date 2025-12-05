// ------------------------------------------------------------
//  Product & Part Graph Schema for Graph-RAG Asset Intelligence
//  Neo4j 5.26.12 (Community Edition)
// ------------------------------------------------------------



// 1. Uniqueness Constraints


// Each Product must have a unique name.
CREATE CONSTRAINT product_name_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.name IS UNIQUE;

// Each Part must have a unique part_id.
CREATE CONSTRAINT part_id_unique IF NOT EXISTS
FOR (p:Part)
REQUIRE p.part_id IS UNIQUE;

// Each Spec (key,value,unit) combination must be unique.
// NODE KEY enforces uniqueness AND existence.
CREATE CONSTRAINT spec_identity IF NOT EXISTS
FOR (s:Spec)
REQUIRE (s.key, s.value, s.unit) IS NODE KEY;



// 2. Property Indexes


// Common filtering index (useful for UI filters and category-level RAG).
CREATE INDEX part_category_idx IF NOT EXISTS
FOR (p:Part)
ON (p.category);

// Optional product SKU index.
CREATE INDEX product_sku_idx IF NOT EXISTS
FOR (p:Product)
ON (p.sku);

// Fast filtering of specs by key.
CREATE INDEX spec_key_idx IF NOT EXISTS
FOR (s:Spec)
ON (s.key);



// 3. Fulltext Index (Neo4j 5 Syntax)

//
// Used for fuzzy keyword search on Part nodes.
// This enables hybrid retrieval (vector + fulltext).
//
CREATE FULLTEXT INDEX part_fulltext_idx IF NOT EXISTS
FOR (p:Part)
ON EACH [p.name, p.description, p.category];



// 4. Embedding Meta Property Index


// Tracks embedding dimension for debugging (optional)
CREATE INDEX part_embedding_dim_idx IF NOT EXISTS
FOR (p:Part)
ON (p.embedding_dim);



// 5. Vector Indexes for Semantic Search

// These are required for the RAG retrieval engine.
// They must match your embedding model dimension (384 = gte-small).
// Neo4j 5 supports vector indexes natively.
//

// Part-level semantic index
CREATE VECTOR INDEX part_embedding_index IF NOT EXISTS
FOR (p:Part)
ON (p.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 384,
    `vector.similarity_function`: "cosine"
  }
};

// Product-level semantic index
CREATE VECTOR INDEX product_embedding_index IF NOT EXISTS
FOR (p:Product)
ON (p.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 384,
    `vector.similarity_function`: "cosine"
  }
};



// 6. Optional Existence Constraints


// Ensure Product has a name
CREATE CONSTRAINT product_name_exists IF NOT EXISTS
FOR (p:Product)
REQUIRE p.name IS NOT NULL;

// (You may add more existence constraints as needed)
// ------------------------------------------------------------
