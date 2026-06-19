const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export async function verifyCertificate(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/verify`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Verification request failed (${response.status})`);
  }

  return response.json();
}

export async function downloadReport(results) {
  const response = await fetch(`${API_BASE_URL}/api/report`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(results),
  });

  if (!response.ok) {
    throw new Error("Report generation failed");
  }

  return response.blob();
}
