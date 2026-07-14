describe("frontend scaffold", () => {
  it("mounts the placeholder app", async () => {
    const { default: App } = await import("../App");
    expect(App).toBeTypeOf("function");
  });
});
