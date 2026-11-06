import { useEffect, useMemo, useState } from "react";
import { api, CATEGORY_LABELS } from "../api.js";

const FILTERS = [
  { key: "all", label: "全部" },
  { key: "top", label: "上装" },
  { key: "bottom", label: "下装" },
  { key: "outerwear", label: "外套" },
  { key: "dress", label: "连衣裙" },
  { key: "shoes", label: "鞋" },
  { key: "bag", label: "包" },
  { key: "accessory", label: "配饰" },
];

export default function Wardrobe({ onChanged }) {
  const [garments, setGarments] = useState([]);
  const [filter, setFilter] = useState("all");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const body = await api.garments("active");
      setGarments(body.garments);
      setError("");
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const visible = useMemo(
    () => (filter === "all" ? garments : garments.filter((item) => item.category === filter)),
    [garments, filter]
  );

  const stash = async (item) => {
    try {
      await api.patchGarment(item.id, { status: "stored" });
      await load();
      onChanged?.();
    } catch (patchError) {
      alert(patchError.message);
    }
  };

  const remove = async (item) => {
    if (!confirm(`删掉「${item.name}」？`)) return;
    try {
      await api.deleteGarment(item.id);
      await load();
      onChanged?.();
    } catch (deleteError) {
      alert(deleteError.message);
    }
  };

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">衣橱</h1>
        <p className="mt-1 text-sm text-muted">
          {loading ? "在数……" : `${garments.length} 件在穿`}
        </p>
      </header>

      <div className="-mx-5 flex gap-2 overflow-x-auto px-5 pb-1">
        {FILTERS.map((item) => (
          <button
            key={item.key}
            onClick={() => setFilter(item.key)}
            className={`chip shrink-0 ${filter === item.key ? "chip-active" : ""}`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {error ? <p className="text-sm text-red-400">{error}</p> : null}

      {!loading && visible.length === 0 ? (
        <div className="card p-5 text-sm text-muted">
          这个分类下还没有衣服。去「入库」加一件。
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3">
        {visible.map((item) => (
          <div key={item.id} className="card overflow-hidden">
            <div
              className="flex h-28 items-center justify-center"
              style={{ backgroundColor: item.color_hex || "#2A2A2E" }}
            >
              {item.cutout_url || item.image_url ? (
                <img
                  src={item.cutout_url || item.image_url}
                  alt={item.name}
                  className="h-full w-full object-cover"
                />
              ) : (
                <span className="text-xs text-black/40">无图</span>
              )}
            </div>
            <div className="p-3">
              <p className="truncate text-sm">{item.name}</p>
              <p className="mt-1 text-[11px] text-muted">
                {CATEGORY_LABELS[item.category]} · 厚薄 {item.warmth} · 正式 {item.formality}
              </p>
              <div className="mt-2 flex gap-1.5">
                <button
                  className="flex-1 rounded-lg border border-edge py-1.5 text-[11px] text-muted active:bg-surface"
                  onClick={() => stash(item)}
                >
                  收起来
                </button>
                <button
                  className="rounded-lg border border-edge px-2 py-1.5 text-[11px] text-muted active:bg-surface"
                  onClick={() => remove(item)}
                >
                  删
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
