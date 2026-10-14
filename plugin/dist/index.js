(function (DFL, React) {
    const { PanelSection, PanelSectionRow, ToggleField, Field } = DFL;

    const Content = ({ serverAPI }) => {
        const [enabled, setEnabled] = React.useState(false);
        const [busy, setBusy] = React.useState(false);
        const [detail, setDetail] = React.useState("проверяю…");

        const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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

        const call = async (name) => {
            try {
                const raw = await serverAPI.callPluginMethod(name, {});
                console.log("[Hiddify] " + name + " ->", JSON.stringify(raw));
                return raw;
            } catch (e) {
                console.error("[Hiddify] " + name + " failed", e);
                return { error: String(e) };
            }
        };

        const refresh = async () => {
            const raw = await call("hiddify_status");
            const s = unwrap(raw, "enabled");
            const on = !!(s && s.enabled);
            setEnabled(on);
            if (on) setDetail("туннель включён");
            else if (s) setDetail("выключен (" + (s.service || "?") + ")");
            else setDetail("нет ответа: " + JSON.stringify(raw).slice(0, 120));
            return on;
        };

        React.useEffect(() => {
            refresh();
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
                        setBusy(true);
                        setDetail(want ? "включаю…" : "выключаю…");
                        const resRaw = await call(want ? "hiddify_up" : "hiddify_down");
                        const res = unwrap(resRaw, "ok");
                        await sleep(300);
                        const on = await refresh();
                        if (!(res && res.ok)) {
                            setDetail((res && res.error) || ("не получилось: " + JSON.stringify(resRaw).slice(0, 120)));
                        } else if (want !== on) {
                            setDetail(want ? "туннель не поднялся" : "туннель ещё поднят");
                        }
                        setBusy(false);
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
