/* Fill these in once the accounts exist; links with an empty value are hidden automatically. */
window.SITE_CONFIG = {
  email: "tiannuo1217@gmail.com",
  linkedin: "https://www.linkedin.com/in/tiannuo-yang",
  github_repo: "https://github.com/tiannuo1217/tiannuo1217.github.io",
  tableau: "",          // Tableau Public dashboard URL, once published
};

document.addEventListener("DOMContentLoaded", () => {
  const cfg = window.SITE_CONFIG;
  document.querySelectorAll("[data-link]").forEach((a) => {
    const key = a.getAttribute("data-link");
    const val = cfg[key];
    if (!val) { a.remove(); return; }
    a.href = key === "email" ? "mailto:" + val : val;
  });
});
