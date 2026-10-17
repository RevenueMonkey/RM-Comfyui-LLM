export function routerMode(router, provider) {
    return router || (provider === "OpenRouter" ? "OpenRouter" : "Direct");
}

export function hostMatches(endpoint, host) {
    return host === "Auto" || endpoint === host || endpoint.startsWith(`${host}/`);
}

export function selectedCapabilities(caps, host) {
    if (!caps || caps.provider !== "OpenRouter" || host === "Auto") return caps;
    const endpoints = caps.endpoints.filter(ep => hostMatches(ep.id, host));
    if (!endpoints.length) return null;
    const parameters = Object.fromEntries(Object.entries(caps.parameters).filter(([name]) => endpoints.every(ep => ep.parameters.includes(name))));
    const limit = name => {
        const values = endpoints.map(ep => ep[name]).filter(n => Number.isInteger(n) && n > 0);
        return values.length ? Math.min(...values) : null;
    };
    return { ...caps, parameters, endpoints: [{ ...endpoints[0], id: host, parameters: Object.keys(parameters), context_length: limit("context_length"), max_tokens: limit("max_tokens") }] };
}
