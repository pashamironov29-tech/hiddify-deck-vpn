import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const srcPath = fileURLToPath(new URL("../plugin/dist/index.js", import.meta.url));
const src = fs.readFileSync(srcPath, "utf8");

test("bundle stays a legacy IIFE", () => {
    assert.match(src, /^\(function \(DFL, React\) \{/);
    assert.match(src, /\}\)\(DFL, SP_REACT\);\s*$/);
    assert.equal(src.includes("export "), false);
    assert.equal(src.includes("import "), false);
});

function createHarness(responders) {
    const calls = [];
    const hooks = [];
    const effects = [];
    let hookIndex = 0;

    const ReactMock = {
        useState(init) {
            const i = hookIndex++;
            if (!Object.prototype.hasOwnProperty.call(hooks, i)) {
                hooks[i] = { v: init };
            }
            return [
                hooks[i].v,
                (next) => {
                    hooks[i].v = typeof next === "function" ? next(hooks[i].v) : next;
                },
            ];
        },
        useRef(init) {
            const i = hookIndex++;
            if (!Object.prototype.hasOwnProperty.call(hooks, i)) {
                hooks[i] = { current: init };
            }
            return hooks[i];
        },
        useEffect(fn) {
            effects.push(fn);
        },
        createElement(type, props, ...children) {
            return { type, props: props || {}, children };
        },
    };

    let factory = null;
    const DFL = {
        PanelSection: "PanelSection",
        PanelSectionRow: "PanelSectionRow",
        ToggleField: "ToggleField",
        staticClasses: { Title: "Title" },
        definePlugin(fn) {
            factory = fn;
            return fn;
        },
    };

    const serverAPI = {
        async callPluginMethod(name, args) {
            calls.push({ name, args });
            const respond = responders[name];
            if (!respond) throw new Error("no responder for " + name);
            return await respond();
        },
    };

    vm.runInNewContext(src, {
        DFL,
        SP_REACT: ReactMock,
        console,
        Promise,
        JSON,
        Object,
        String,
        Error,
        setTimeout(fn) {
            fn();
            return 0;
        },
    });

    function findToggle(node) {
        if (!node || typeof node !== "object") return null;
        if (node.type === "ToggleField") return node;
        for (const child of node.children || []) {
            const found = findToggle(child);
            if (found) return found;
        }
        return null;
    }

    function render() {
        hookIndex = 0;
        effects.length = 0;
        const plugin = factory(serverAPI);
        const view = plugin.content.type(plugin.content.props);
        return { plugin, toggle: findToggle(view) };
    }

    async function flushEffects() {
        const pending = effects.splice(0).map((fn) => fn());
        await new Promise((resolve) => setImmediate(resolve));
        await new Promise((resolve) => setImmediate(resolve));
        return pending;
    }

    return { calls, render, flushEffects };
}

async function mount(responders) {
    const harness = createHarness(responders);
    const first = harness.render();
    await harness.flushEffects();
    const shown = harness.render();
    return { harness, toggle: shown.toggle, plugin: first.plugin };
}

test("initial status renders active, inactive, failed, and unknown", async () => {
    const cases = [
        [{ enabled: true, service: "active", tun: true }, true, "туннель включён"],
        [{ enabled: false, service: "inactive", tun: false }, false, "выключен (inactive)"],
        [{ enabled: false, service: "failed", tun: true }, false, "выключен (failed)"],
        [{ enabled: false, service: "unknown", tun: false }, false, "выключен (unknown)"],
        [{ enabled: false, service: "", tun: false }, false, "выключен (?)"],
    ];
    for (const [payload, checked, detail] of cases) {
        const { toggle } = await mount({
            hiddify_status: async () => payload,
        });
        assert.equal(toggle.props.checked, checked, detail);
        assert.equal(toggle.props.description, detail);
        assert.equal(toggle.props.disabled, false);
    }
});

test("unwraps Decky result wrappers and JSON strings", async () => {
    const wrapped = await mount({
        hiddify_status: async () => ({
            success: true,
            result: { enabled: true, service: "active", tun: true },
        }),
    });
    assert.equal(wrapped.toggle.props.checked, true);
    assert.equal(wrapped.toggle.props.description, "туннель включён");

    const nested = await mount({
        hiddify_status: async () => ({
            result: { result: { enabled: false, service: "failed", tun: false } },
        }),
    });
    assert.equal(nested.toggle.props.checked, false);
    assert.equal(nested.toggle.props.description, "выключен (failed)");

    const encoded = await mount({
        hiddify_status: async () =>
            JSON.stringify({ enabled: false, service: "inactive", tun: false }),
    });
    assert.equal(encoded.toggle.props.description, "выключен (inactive)");
});

test("a circular status payload is still applied", async () => {
    const { toggle } = await mount({
        hiddify_status: async () => {
            const payload = { enabled: true, service: "active", tun: true };
            payload.self = payload;
            return payload;
        },
    });
    assert.equal(toggle.props.checked, true);
    assert.equal(toggle.props.description, "туннель включён");
});

test("status command error does not flip a live toggle off", async () => {
    const responders = {
        hiddify_status: async () => ({ enabled: true, service: "active", tun: true }),
        hiddify_down: async () => ({ ok: true, error: "" }),
    };
    const { harness, toggle } = await mount(responders);
    assert.equal(toggle.props.checked, true);

    responders.hiddify_status = async () => ({
        enabled: false,
        service: "unknown",
        tun: false,
        error: "Failed to connect to bus: No such file or directory",
    });
    await toggle.props.onChange(false);
    const after = harness.render().toggle;
    assert.equal(after.props.checked, true);
    assert.match(after.props.description, /Failed to connect to bus/);
    assert.equal(after.props.disabled, false);
});

test("toggle on and off calls the matching method and clears busy", async () => {
    const responders = {
        hiddify_status: async () => ({ enabled: false, service: "inactive", tun: false }),
        hiddify_up: async () => ({ ok: true, error: "" }),
        hiddify_down: async () => ({ ok: true, error: "" }),
    };
    const { harness, toggle } = await mount(responders);
    assert.equal(toggle.props.checked, false);
    assert.equal(harness.calls[0].name, "hiddify_status");
    assert.equal(JSON.stringify(harness.calls[0].args), "{}");

    responders.hiddify_status = async () => ({ enabled: true, service: "active", tun: true });
    await toggle.props.onChange(true);
    let shown = harness.render().toggle;
    assert.equal(shown.props.checked, true);
    assert.equal(shown.props.description, "туннель включён");
    assert.equal(shown.props.disabled, false);
    assert.equal(harness.calls.at(-2).name, "hiddify_up");
    assert.equal(JSON.stringify(harness.calls.at(-2).args), "{}");

    responders.hiddify_status = async () => ({ enabled: false, service: "inactive", tun: false });
    await shown.props.onChange(false);
    shown = harness.render().toggle;
    assert.equal(shown.props.checked, false);
    assert.equal(shown.props.description, "выключен (inactive)");
    assert.equal(harness.calls.at(-2).name, "hiddify_down");
});

test("toggle surfaces start errors, mismatches, and res wrappers", async () => {
    const responders = {
        hiddify_status: async () => ({ enabled: false, service: "inactive", tun: false }),
        hiddify_up: async () => ({ ok: false, error: "systemctl start failed" }),
    };
    const failed = await mount(responders);
    await failed.toggle.props.onChange(true);
    let shown = failed.harness.render().toggle;
    assert.equal(shown.props.checked, false);
    assert.equal(shown.props.description, "systemctl start failed");
    assert.equal(shown.props.disabled, false);

    const mismatch = await mount({
        hiddify_status: async () => ({ enabled: false, service: "inactive", tun: false }),
        hiddify_up: async () => ({ ok: true, error: "" }),
    });
    await mismatch.toggle.props.onChange(true);
    shown = mismatch.harness.render().toggle;
    assert.equal(shown.props.description, "туннель не поднялся");

    const wrapped = await mount({
        hiddify_status: async () => ({ enabled: true, service: "active", tun: true }),
        hiddify_down: async () => ({ res: { ok: false, error: "stop refused" } }),
    });
    await wrapped.toggle.props.onChange(false);
    shown = wrapped.harness.render().toggle;
    assert.equal(shown.props.description, "stop refused");
    assert.equal(shown.props.disabled, false);
});

test("a second toggle while busy is ignored", async () => {
    let release = () => {};
    const responders = {
        hiddify_status: async () => ({ enabled: false, service: "inactive", tun: false }),
        hiddify_up: () =>
            new Promise((resolve) => {
                release = () => resolve({ ok: true, error: "" });
            }),
    };
    const { harness, toggle } = await mount(responders);
    const first = toggle.props.onChange(true);
    await new Promise((resolve) => setImmediate(resolve));
    const second = toggle.props.onChange(true);
    await second;
    release();
    await first;
    const ups = harness.calls.filter((call) => call.name === "hiddify_up");
    assert.equal(ups.length, 1);
    assert.equal(harness.render().toggle.props.disabled, false);
});

test("garbage status keeps the previous toggle and shows no-response", async () => {
    const responders = {
        hiddify_status: async () => ({ enabled: true, service: "active", tun: true }),
        hiddify_down: async () => ({ ok: true, error: "" }),
    };
    const { harness, toggle } = await mount(responders);
    responders.hiddify_status = async () => "not-json";
    await toggle.props.onChange(false);
    const shown = harness.render().toggle;
    assert.equal(shown.props.checked, true);
    assert.match(shown.props.description, /^нет ответа: /);
    assert.equal(shown.props.disabled, false);
});
