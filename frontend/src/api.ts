export interface QueryResponse {
  answer: string;
  context: {
    question: string;
    parts: {
      part_id: string;
      name: string;
      category: string;
      description: string;
      score: number;
      specs: { key: string; value: any; unit: string }[];
      products: string[];
    }[];
    compatibility: {
      [part_id: string]: {
        to_id: string;
        score: number;
        explanations: string[];
      }[];
    };
  };
}

const API_BASE = "http://localhost:8000";

export async function sendQuery(question: string): Promise<QueryResponse> {
  const res = await fetch(`${API_BASE}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, k_parts: 5 })
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}
