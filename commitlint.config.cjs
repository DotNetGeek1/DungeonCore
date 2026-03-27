module.exports = {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "type-enum": [
      2,
      "always",
      [
        "feat",
        "fix",
        "docs",
        "refactor",
        "test",
        "perf",
        "chore",
        "ci",
        "build",
        "style"
      ]
    ],
    "subject-empty": [2, "never"],
    "type-empty": [2, "never"],
    "header-max-length": [2, "always", 100]
  },
  prompt: {
    messages: {
      type: "Choose the type of change:",
      subject: "Write a short, clear summary (lore optional):"
    }
  }
};
