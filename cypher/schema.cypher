// ---------------------
// SCHEMA INITIALIZATION
// ---------------------

CREATE CONSTRAINT product_name_unique IF NOT EXISTS
FOR (p:Product) REQUIRE p.name IS UNIQUE;

CREATE CONSTRAINT part_id_unique IF NOT EXISTS
FOR (p:Part) REQUIRE p.part_id IS UNIQUE;

CREATE CONSTRAINT spec_key_value_unique IF NOT EXISTS
FOR (s:Spec) REQUIRE (s.key, s.value, s.unit) IS UNIQUE;

// ---------------------
// VECTOR INDEXES
// ---------------------

// document chunk embeddings
CREATE VECTOR INDEX chunk_embedding_index IF NOT EXISTS
FOR (c:Chunk) ON (c.embedding)
OPTIONS { indexConfig: { `vector.dimensions`: 384, `vector.similarity_function`: 'cosine' } };

// part embeddings
CREATE VECTOR INDEX part_embedding_index IF NOT EXISTS
FOR (p:Part) ON (p.embedding)
OPTIONS { indexConfig: { `vector.dimensions`: 384, `vector.similarity_function`: 'cosine' } };

// product embeddings
CREATE VECTOR INDEX product_embedding_index IF NOT EXISTS
FOR (p:Product) ON (p.embedding)
OPTIONS { indexConfig: { `vector.dimensions`: 384, `vector.similarity_function`: 'cosine' } };

// ---------------------
// BASE RELATIONSHIPS
// ---------------------
