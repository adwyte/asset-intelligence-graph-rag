export interface ProductInfo {
  name: string;
  sku?: string;
}

export interface RetrievedSpec {
  key: string;
  value: any;
  unit: string;
}

export interface RetrievedPart {
  part_id: string;
  name: string;
  category: string;
  description: string;
  score: number;
  source: string;
  specs: RetrievedSpec[];
  products: string[];
}

export interface QueryResponse {
  answer: string;
  context: {
    question: string;
    product_name?: string | null;
    parts: RetrievedPart[];
    compatibility: {
      [part_id: string]: {
        to_id: string;
        score: number;
        explanations: string[];
      }[];
    };
  };
}

export interface CompatPair {
  part_a_id: string;
  part_a_name: string;
  part_b_id: string;
  part_b_name: string;
  score: number;
  mechanical: number;
  functional: number;
  semantic: number;
  hierarchy: number;
  explanations: string[];
}

export interface NewPartCompatResult {
  existing_part_id: string;
  existing_part_name: string;
  existing_part_category: string;
  assemblies: string[];
  score: number;
  mechanical: number;
  functional: number;
  semantic: number;
  hierarchy: number;
  explanations: string[];
}

const API_BASE = "http://localhost:8000";

export async function fetchProducts(): Promise<ProductInfo[]> {
  const res = await fetch(`${API_BASE}/api/products`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  const data = await res.json();
  return data.products || [];
}

export async function sendQuery(
  question: string,
  productName?: string | null,
): Promise<QueryResponse> {
  const res = await fetch(`${API_BASE}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      k_parts: 5,
      product_name: productName || null,
    }),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function fetchProductCompat(
  productName: string,
): Promise<CompatPair[]> {
  const res = await fetch(
    `${API_BASE}/api/compat/product/${encodeURIComponent(productName)}`,
  );
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  const data = await res.json();
  return data.pairs || [];
}

export interface NewPartCompatRequest {
  product_name: string;
  description: string;
  category?: string;
  specs?: Record<string, { value: any; unit?: string }>;
  assembly_hint?: string;
  top_k?: number;
}

export async function fetchNewPartCompat(
  payload: NewPartCompatRequest,
): Promise<NewPartCompatResult[]> {
  const res = await fetch(`${API_BASE}/api/compat/new-part`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  const data = await res.json();
  return data.results || [];
}

export async function uploadAudioAndTranscribe(blob: Blob): Promise<string> {
  const formData = new FormData();
  formData.append("file", blob, "audio.webm");

  const res = await fetch(`${API_BASE}/api/stt`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  const data = await res.json();
  return data.text || "";
}


export async function uploadDocument(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/api/docs/upload`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) throw new Error("Document upload failed");

  const data = await res.json();
  return data.filename;
}

export async function uploadYaml(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/api/docs/upload-yaml`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) throw new Error("YAML upload failed");

  const data = await res.json();
  return data.status || "ok";
}
