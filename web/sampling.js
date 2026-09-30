export function creativityToSampling(creativity) {
    const c = Math.max(0, Math.min(100, creativity)) / 100;
    return { temperature: Math.round(0.2 * 6 ** c * 100) / 100, top_p: Math.round((1 - 0.1 * 10 ** -c) * 100) / 100 };
}

export function samplingToCreativity(name, value) {
    const c = name === "temperature"
        ? Math.log(value / 0.2) / Math.log(6)
        : -Math.log10((1 - value) / 0.1);
    return Math.max(0, Math.min(100, c * 100));
}
