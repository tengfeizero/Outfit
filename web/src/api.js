const request = async (url, options = {}) => {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = `请求失败（${response.status}）`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* 响应不是 JSON，用默认文案 */
    }
    throw new Error(detail);
  }
  return response.json();
};

const jsonPost = (url, payload) =>
  request(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export const api = {
  status: () => request("/api/status"),
  occasions: () => request("/api/occasions"),

  profile: () => request("/api/profile"),
  saveProfile: (payload) =>
    request("/api/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  garments: (status = "active") => request(`/api/garments?status=${status}`),
  createGarment: (payload) => jsonPost("/api/garments", payload),
  autotag: (image_path) => jsonPost("/api/garments/autotag", { image_path }),
  patchGarment: (id, payload) =>
    request(`/api/garments/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  deleteGarment: (id) => request(`/api/garments/${id}`, { method: "DELETE" }),

  upload: async (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/api/upload", { method: "POST", body: form });
  },

  plan: (occasion, temp_c, text = "") => jsonPost("/api/plan", { occasion, temp_c, text }),
  saveOutfit: (payload) => jsonPost("/api/outfits", payload),
  markWorn: (id) => jsonPost(`/api/outfits/${id}/worn`, {}),

  weather: () => request("/api/weather"),
  setCity: (city) => jsonPost("/api/weather/city", { city }),

  render: (payload) => jsonPost("/api/render", payload),
  shopping: (payload) => jsonPost("/api/shopping", payload),
};

export const CATEGORY_LABELS = {
  top: "上装",
  bottom: "下装",
  outerwear: "外套",
  dress: "连衣裙",
  shoes: "鞋",
  bag: "包",
  accessory: "配饰",
};
