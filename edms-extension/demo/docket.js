// Demo docket — swaps case data when the user clicks the toolbar buttons.

const CASES = {
  civil: {
    caption: "State of Iowa v. Acme Holdings LLC",
    caseNumber: "CVCV012345",
    caseType: "Civil — Contract",
    county: "Polk",
    judge: "Hon. Margaret Smith",
    filedDate: "2024-03-15",
    filings: [
      { date: "2024-03-15", title: "Petition at Law", filer: "Plaintiff" },
      { date: "2024-03-22", title: "Answer and Affirmative Defenses", filer: "Defendant" },
      { date: "2024-04-08", title: "Motion to Dismiss", filer: "Defendant" },
      { date: "2024-04-19", title: "Resistance to Motion to Dismiss", filer: "Plaintiff" },
      { date: "2024-05-02", title: "Order on Motion to Dismiss", filer: "Court" },
      { date: "2024-05-30", title: "Scheduling Order", filer: "Court" },
    ],
  },
  juvenile: {
    caption: "In the Interest of A.B., a minor child",
    caseNumber: "JDJV004821",
    caseType: "Juvenile — Delinquency",
    county: "Linn",
    judge: "Hon. Daniel Reyes",
    filedDate: "2024-02-04",
    filings: [
      { date: "2024-02-04", title: "Petition", filer: "State" },
      { date: "2024-02-12", title: "Detention Order", filer: "Court" },
      { date: "2024-03-01", title: "Adjudication Hearing Notice", filer: "Court" },
      { date: "2024-03-18", title: "Dispositional Report", filer: "JCO" },
    ],
  },
  dissolution: {
    caption: "In re the Marriage of Doe and Doe",
    caseNumber: "DMDM007734",
    caseType: "Domestic Relations — Dissolution",
    county: "Johnson",
    judge: "Hon. Patricia Lin",
    filedDate: "2024-01-22",
    filings: [
      { date: "2024-01-22", title: "Petition for Dissolution of Marriage", filer: "Petitioner" },
      { date: "2024-02-05", title: "Answer", filer: "Respondent" },
      { date: "2024-03-10", title: "Temporary Matters Affidavit", filer: "Petitioner" },
      { date: "2024-04-02", title: "Decree of Dissolution", filer: "Court" },
    ],
  },
};

const els = {
  caption: document.querySelector('[data-cv-field="caption"]'),
  caseNumber: document.querySelector('[data-cv-field="case-number"]'),
  caseType: document.querySelector('[data-cv-field="case-type"]'),
  county: document.querySelector('[data-cv-field="county"]'),
  judge: document.querySelector('[data-cv-field="judge"]'),
  filedDate: document.querySelector('[data-cv-field="filed-date"]'),
  list: document.getElementById("filingsList"),
  toolbar: document.querySelectorAll(".mock-toolbar__btn"),
};

function renderCase(key) {
  const c = CASES[key];
  els.caption.textContent = c.caption;
  els.caseNumber.textContent = c.caseNumber;
  els.caseType.textContent = c.caseType;
  els.county.textContent = c.county;
  els.judge.textContent = c.judge;
  els.filedDate.textContent = c.filedDate;

  els.list.innerHTML = "";
  c.filings.forEach((f) => {
    const li = document.createElement("li");
    li.className = "filing";
    li.dataset.cvFilingRow = "";
    li.dataset.cvDocTitle = f.title;

    const date = document.createElement("div");
    date.className = "filing__date";
    date.textContent = f.date;

    const title = document.createElement("div");
    title.innerHTML = `<div class="filing__title">${f.title}</div><div class="filing__filer">Filed by ${f.filer}</div>`;

    const dl = document.createElement("a");
    dl.className = "filing__download";
    dl.textContent = "Download PDF";
    dl.href = "#";
    dl.addEventListener("click", (e) => e.preventDefault());

    const slot = document.createElement("div");
    slot.dataset.cvActionSlot = "";

    li.appendChild(date);
    li.appendChild(title);
    li.appendChild(dl);
    li.appendChild(slot);
    els.list.appendChild(li);
  });

  // Tell the content script to re-scan the docket
  document.dispatchEvent(new CustomEvent("cv:rescrape"));
}

els.toolbar.forEach((btn) => {
  btn.addEventListener("click", () => {
    els.toolbar.forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    // Remove old EDMSpro injections so they re-render
    document.querySelectorAll(".cv-banner, .cv-action").forEach((n) => n.remove());
    renderCase(btn.dataset.case);
  });
});

renderCase("civil");
