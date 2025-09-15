// Uniqueness
CREATE CONSTRAINT product_name_unique IF NOT EXISTS
FOR (p:Product) REQUIRE p.name IS UNIQUE;

CREATE CONSTRAINT part_id_unique IF NOT EXISTS
FOR (p:Part) REQUIRE p.part_id IS UNIQUE;

CREATE CONSTRAINT supplier_name_unique IF NOT EXISTS
FOR (s:Supplier) REQUIRE s.name IS UNIQUE;

CREATE CONSTRAINT material_name_unique IF NOT EXISTS
FOR (m:Material) REQUIRE m.name IS UNIQUE;

CREATE CONSTRAINT document_id_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.doc_id IS UNIQUE;

CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS
FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE;

// Lookups
CREATE INDEX part_name IF NOT EXISTS FOR (p:Part) ON (p.name);
CREATE INDEX doc_name IF NOT EXISTS FOR (d:Document) ON (d.name);
CREATE INDEX spec_key IF NOT EXISTS FOR (s:Spec) ON (s.key);

// Vector indexes (default 384d; change if you use a different model)
CREATE VECTOR INDEX chunk_embedding_index IF NOT EXISTS
FOR (c:Chunk) ON (c.embedding)
OPTIONS { indexConfig: { `vector.dimensions`: 384, `vector.similarity_function`: 'cosine' } };

CREATE VECTOR INDEX part_embedding_index IF NOT EXISTS
FOR (p:Part) ON (p.embedding)
OPTIONS { indexConfig: { `vector.dimensions`: 384, `vector.similarity_function`: 'cosine' } };
