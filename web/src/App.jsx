import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import Today from "./pages/Today.jsx";
import Wardrobe from "./pages/Wardrobe.jsx";
import AddItem from "./pages/AddItem.jsx";
import Profile from "./pages/Profile.jsx";

const TABS = [
  { key: "today", label: "今天", glyph: "◐" },
  { key: "wardrobe", label: "衣橱", glyph: "▤" },
  { key: "add", label: "入库", glyph: "＋" },
  { key: "profile", label: "我的", glyph: "◍" },
];

const readTab = () => {
  const hash = window.location.hash.replace("#", "");
  return TABS.some((item) => item.key === hash) ? hash : "today";
};

export default function App() {
  const [tab, setTab] = useState(readTab);
  const [status, setStatus] = useState(null);
  const [offline, setOffline] = useState("");

  useEffect(() => {
    const onHashChange = () => setTab(readTab());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const go = (key) => {
    setTab(key);
    window.location.hash = key;
  };

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.status());
      setOffline("");
    } catch (error) {
      setOffline(error.message);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="min-h-full overflow-x-hidden bg-ink">
      <main className="mx-auto w-full max-w-md px-5 pb-28 pt-8">
        {offline ? (
          <div className="card p-4 text-sm text-muted">
            <p className="text-paper">连不上本地服务</p>
            <p className="mt-1">{offline}</p>
            <p className="mt-2 text-xs">
              确认笔记本上的服务还在跑（那个打印二维码的窗口没关）。
            </p>
          </div>
        ) : null}

        {tab === "today" && <Today status={status} onRecorded={refresh} />}
        {tab === "wardrobe" && <Wardrobe onChanged={refresh} />}
        {tab === "add" && <AddItem onAdded={() => { refresh(); go("wardrobe"); }} />}
        {tab === "profile" && <Profile status={status} onSaved={refresh} />}
      </main>

      <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-edge bg-ink/95 backdrop-blur">
        <div className="safe-bottom mx-auto flex w-full max-w-md items-stretch">
          {TABS.map((item) => (
            <button
              key={item.key}
              onClick={() => go(item.key)}
              className={`flex flex-1 flex-col items-center gap-1 py-3 text-[11px] transition-colors ${
                tab === item.key ? "text-brass" : "text-muted"
              }`}
            >
              <span className="text-base leading-none">{item.glyph}</span>
              {item.label}
            </button>
          ))}
        </div>
      </nav>
    </div>
  );
}
