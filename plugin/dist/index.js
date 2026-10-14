(function (DFL, React) {
    const { PanelSection, PanelSectionRow, ToggleField } = DFL;

    const safeJson = (value) => {
        try {
            const text = JSON.stringify(value);
            return text === undefined ? String(value) : text;
        } catch (e) {
            return String(e);
        }
    };

    const brief = (value) => safeJson(value).slice(0, 120);

    // Accepts: raw dict, {success,result}, {result:{...}}, nested wraps, JSON strings.
    const unwrap = (r, key) => {
        let v = r;
        for (let i = 0; i < 5; i++) {
            if (typeof v === "string") {
                try { v = JSON.parse(v); } catch (e) { return null; }
                continue;
            }
            if (!v || typeof v !== "object") return null;
            if (key in v) return v;
            if ("result" in v) { v = v.result; continue; }
            if ("res" in v) { v = v.res; continue; }
            return null;
        }
        return null;
    };

    const applyStatus = (prevEnabled, raw) => {
        const s = unwrap(raw, "enabled");
        if (!s || s.error) {
            const detail = (s && s.error) || ("нет ответа: " + brief(raw));
            return { known: false, enabled: prevEnabled, detail: detail };
        }
        const on = !!s.enabled;
        const detail = on ? "туннель включён" : ("выключен (" + (s.service || "?") + ")");
        return { known: true, enabled: on, detail: detail };
    };

    const Content = ({ serverAPI }) => {
        const [enabled, setEnabled] = React.useState(false);
        const [busy, setBusy] = React.useState(false);
        const [detail, setDetail] = React.useState("проверяю…");
        const alive = React.useRef(true);
        const busyRef = React.useRef(false);
        const refreshGen = React.useRef(0);

        const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

        const call = async (name) => {
            try {
                const raw = await serverAPI.callPluginMethod(name, {});
                console.log("[Hiddify] " + name + " ->", safeJson(raw));
                return raw;
            } catch (e) {
                console.error("[Hiddify] " + name + " failed", e);
                return { error: String(e) };
            }
        };

        const refresh = async () => {
            const gen = ++refreshGen.current;
            const raw = await call("hiddify_status");
            const next = applyStatus(enabled, raw);
            if (!alive.current || gen !== refreshGen.current) {
                return { stale: true, known: false, enabled: enabled };
            }
            if (next.known) setEnabled(next.enabled);
            setDetail(next.detail);
            return { stale: false, known: next.known, enabled: next.known ? next.enabled : enabled };
        };

        React.useEffect(() => {
            alive.current = true;
            refresh().catch((e) => {
                if (alive.current) setDetail("нет ответа: " + String(e));
            });
            return () => { alive.current = false; };
        }, []);

        return React.createElement(
            PanelSection,
            { title: "VPN", spinner: busy },
            React.createElement(
                PanelSectionRow,
                null,
                React.createElement(ToggleField, {
                    label: "Hiddify",
                    description: detail,
                    checked: enabled,
                    disabled: busy,
                    onChange: async (want) => {
                        if (busyRef.current) return;
                        busyRef.current = true;
                        setBusy(true);
                        setDetail(want ? "включаю…" : "выключаю…");
                        try {
                            const resRaw = await call(want ? "hiddify_up" : "hiddify_down");
                            const res = unwrap(resRaw, "ok");
                            await sleep(300);
                            const status = await refresh();
                            if (!alive.current || status.stale) return;
                            if (!(res && res.ok)) {
                                setDetail((res && res.error) || ("не получилось: " + brief(resRaw)));
                            } else if (status.known && want !== status.enabled) {
                                setDetail(want ? "туннель не поднялся" : "туннель ещё поднят");
                            }
                        } catch (e) {
                            if (alive.current) setDetail("не получилось: " + String(e));
                        } finally {
                            busyRef.current = false;
                            if (alive.current) setBusy(false);
                        }
                    },
                })
            )
        );
    };

    return DFL.definePlugin((serverApi) => ({
        title: React.createElement(
            "div",
            { className: DFL.staticClasses.Title },
            "Hiddify"
        ),
        content: React.createElement(Content, { serverAPI: serverApi }),
        icon: "🌐",
    }));
})(DFL, SP_REACT);
