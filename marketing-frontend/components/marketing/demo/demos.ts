// The three living shots, as screenplays. Every string here is real corpus
// output (the 614.1(9) answer, the 668.3 text, the comparative-fault hits) —
// the honesty rule for these loops is that nothing is shown the product would
// not actually produce. One exception, marked below: the Compare-editions
// diff words are placeholders until a real edition diff is wired in.

import { el, inkIcon, rail, searchIcon, words } from "./chrome";
import type { Demo } from "./engine";

const QUESTION =
	"What is the statute of limitations for a medical malpractice claim in Iowa?";

// ---------------------------------------------------------------------------
// Assistant: ask → research run → verified answer → source on hover
// ---------------------------------------------------------------------------

export const assistant: Demo = {
	key: "assistant",
	stepCopy: [
		[
			"Ask in plain language, or by citation number.",
			"The assistant shows its work as it goes: what it searched and which sections it read.",
		],
		[
			"It answers from the controlling text, and nothing else.",
			"Retrieval runs against the human-reviewed corpus. No support in the record, no answer.",
		],
		[
			"Every quote and citation is verified before you see it.",
			"A deterministic pass checks each one against its source; anything superseded or overruled is flagged, not quietly served. The source is one click away.",
		],
	],
	phases: [0, 3200, 7600],
	total: 14600,
	captions: [
		[0, "Typing the question"],
		[2900, "Sent"],
		[3200, "Research run · searching the corpus"],
		[5000, "Reading Iowa Code 614.1(9)"],
		[7600, "Verifying 8 citations and 4 quotes"],
		[9600, "Answer streams with verified citations"],
		[12400, "Hover a citation: the source text, one click away"],
	],
	build(st) {
		st.appendChild(rail(1));
		const top = el("div", "topbar");
		top.innerHTML = `<span class="crumb">Hudson Corpus &nbsp;/&nbsp; <b>All sources</b></span><div class="searchbox">${searchIcon()}<span>Search Iowa law…</span><span class="kbd">⌘K</span></div><div class="sel">All sources</div><div class="sel">GPT-5 Mini</div>`;
		st.appendChild(top);
		const side = el("div", "a-side");
		side.innerHTML = `<span class="eyebrow">Chats</span><span class="new">New chat +</span><div style="margin-top:22px" class="eyebrow">Today</div><div class="chatrow" id="chatrow">What is the statute of limitatio…</div>`;
		st.appendChild(side);
		const main = el("div", "a-main");
		main.innerHTML = `
			<div class="a-scroll">
				<div class="a-user" id="user">${QUESTION}</div>
				<div class="run" id="run">
					<div class="hd"><span>RESEARCH RUN</span><span id="timer">0.0 s</span></div>
					<div class="row" id="r1"><div class="tick spin" id="t1"></div><span>Searching the corpus</span><span class="tail" id="tail1"></span></div>
					<div class="row" id="r2"><div class="tick spin" id="t2"></div><span>Reading section</span><span class="tail" id="tail2"></span></div>
					<div class="row" id="r3"><div class="tick spin" id="t3"></div><span>Verifying citations</span><span class="tail" id="tail3"></span></div>
				</div>
				<div class="ans" id="ans">
					<h4 id="ansh">Short answer</h4>
					<p id="p1">${words("The general statute of limitations for medical-malpractice claims in Iowa is two years.")} <span class="cite w" id="c1">Iowa Code § 614.1(9)</span> ${words("The clock starts when the claimant knew, or through reasonable diligence should have known, of the injury.")}</p>
					<p id="p2" style="margin-top:10px">${words("Six-year repose: “in no event shall any action be brought more than six years after the date on which occurred the act or omission or occurrence alleged in the action to have been the cause of the injury or death.”")} <span class="cite w" id="c2">Iowa Code § 614.1(9)(a)</span></p>
					<div class="hover" id="hov" style="left:0;top:0">
						<span class="eyebrow">Iowa Code · 614.1(9) · effective Jan 1, 2025</span>
						<div class="t">Malpractice</div>
						<div class="x">Those founded on injuries to the person or wrongful death against any physician … arising out of patient care, <mark>within two years after the date on which the claimant knew</mark>, or through the use of reasonable diligence should have known … of the injury or death for which damages are sought.</div>
						<div class="l">Open section 614.1 · Verified quote</div>
					</div>
				</div>
			</div>
			<div class="composer">
				<div class="box"><span class="q" id="qtext"></span><span class="caret" id="caret"></span><span style="margin-left:6px" id="ph">Message the assistant…</span><div class="send">${inkIcon("send")}</div></div>
				<div class="foot"><span><span class="eyebrow">Tools</span> &nbsp; Verify Document</span><span>Answers are verified against source text before display.</span></div>
			</div>`;
		st.appendChild(main);
	},
	steps: [
		[
			100,
			function () {
				this.moveTo("#qtext", 60, 26);
			},
		],
		[
			300,
			function () {
				this.style("#ph", "display", "none");
				this.type("#qtext", QUESTION, 2300);
			},
		],
		[
			2700,
			function () {
				this.moveTo(".send", 18, 16);
			},
		],
		[
			2950,
			function () {
				this.click();
				this.text("#qtext", "");
				this.style("#ph", "display", "");
				this.show("#user");
				this.show("#chatrow");
				this.moveCursor(1000, 640);
			},
		],
		[
			3200,
			function () {
				this.show("#run");
				this.show("#r1");
				this.count("#timer", 196, 9000, (v) => `${(v / 10).toFixed(1)} s`);
			},
		],
		[
			4600,
			function () {
				this.removeClass("#t1", "spin");
				this.addClass("#t1", "ok");
				this.text(
					"#tail1",
					"“Iowa medical malpractice statute of limitations Iowa Code …”",
				);
			},
		],
		[
			5000,
			function () {
				this.show("#r2");
			},
		],
		[
			6600,
			function () {
				this.removeClass("#t2", "spin");
				this.addClass("#t2", "ok");
				this.text("#tail2", "614.1(9)");
			},
		],
		[
			7600,
			function () {
				this.show("#r3");
				this.count(
					"#tail3",
					8,
					1800,
					(v) =>
						`${v} of 8 citations · ${Math.min(4, Math.round(v / 2))} of 4 quotes verified`,
				);
			},
		],
		[
			9600,
			function () {
				this.removeClass("#t3", "spin");
				this.addClass("#t3", "ok");
				this.style("#ansh", "opacity", "1");
				this.stream("#p1", 1500);
			},
		],
		[
			10400,
			function () {
				this.addClass("#c1", "ok");
			},
		],
		[
			11300,
			function () {
				this.stream("#p2", 1300);
			},
		],
		[
			12000,
			function () {
				this.addClass("#c2", "ok");
			},
		],
		[
			12400,
			function () {
				this.moveTo("#c1", 40, 10);
			},
		],
		[
			13100,
			function () {
				this.hoverCard("#hov", "#c1", "#ans");
			},
		],
	],
};

// ---------------------------------------------------------------------------
// Reader: go to 668.3 → read → hover a cross reference → compare editions
// ---------------------------------------------------------------------------

export const reader: Demo = {
	key: "reader",
	stepCopy: [
		[
			"Go straight to a section by number.",
			"Type 668.3 anywhere. Suggest resolves it to the Iowa Code, the Admin Code or a case before you press enter.",
		],
		[
			"Read the text as it is in force today.",
			"Effective date, current-status badge, and every in-text cross reference resolved to the section it names.",
		],
		[
			"See exactly what changed between editions.",
			"Compare editions lays this year over last and marks the words that moved, so a stale memory of the statute never survives contact with the page.",
		],
	],
	phases: [0, 3000, 8200],
	total: 13400,
	captions: [
		[0, "Typing a section number"],
		[1400, "Suggest resolves it before enter"],
		[3000, "Reader: 668.3, effective Jan 1, 2025"],
		[5600, "Hover a cross reference to 668.7"],
		[8200, "Compare editions: 2025 over 2024"],
		[10600, "Two words changed, nothing else"],
	],
	build(st) {
		st.appendChild(rail(0));
		const top = el("div", "topbar");
		top.innerHTML = `<span class="crumb" id="crumb">Library</span><div class="searchbox" id="sb">${searchIcon()}<span class="q" id="rq"></span><span class="caret"></span><span id="rph" style="margin-left:6px">Search this section or all Iowa law…</span><span class="kbd">⌘K</span>
			<div class="suggest" id="sug">
				<div class="s hot"><span class="k">Iowa Code</span>668.3 · Comparative fault — effect — payment method<span class="m">section</span></div>
				<div class="s"><span class="k">Iowa Code</span>668.3A · Comparative fault — actions against tortfeasors<span class="m">section</span></div>
				<div class="s"><span class="k">Case</span>Slager v. HWA Corp., 435 N.W.2d 349 (Iowa 1989)<span class="m">cites 668.3</span></div>
			</div></div>
			<span class="topbtn">${inkIcon("copy")}Copy citation</span><span class="topbtn" id="cmpbtn">${inkIcon("compare")}Compare editions</span><span class="topbtn">${inkIcon("print")}Print</span>`;
		st.appendChild(top);
		const main = el("div", "r-main");
		main.innerHTML = `
			<div class="fade" id="rd">
				<span class="eyebrow">Iowa Code · Iowa Code 668</span>
				<h2>668.3 — Comparative fault — effect — payment method</h2>
				<div class="eff">Effective Jan 1, 2025 <span class="badge now">Currently effective</span> <span class="badge fade" id="cmpbadge">Comparing with 2024 edition</span></div>
				<hr>
				<ol>
					<li><span class="mono" style="color:#525252">a.</span> Contributory fault shall not bar recovery in an action by a claimant to recover damages for fault resulting in death or in injury to person or property unless the claimant bears a greater percentage of fault than the combined percentage of fault attributed to the defendants, third-party defendants and persons who have been released pursuant to <span class="ref" id="ref1">section 668.7</span>, but any damages allowed shall be diminished in proportion to the amount of fault attributable to the claimant.</li>
					<li><span class="mono" style="color:#525252">b.</span> Contributory fault shall not bar recovery in an action by a claimant to recover damages for loss of services, companionship, society, or consortium, unless the fault attributable to the person whose injury or death provided the basis for the damages is greater in percentage than the combined percentage of fault attributable to the defendants, third-party defendants, and persons who have been released pursuant to <span class="ref">section 668.7</span> <span id="d1"></span><span id="i1"></span>, but any damages allowed shall be diminished in proportion to the amount of fault attributable to the person whose injury or death provided the basis for the damages.</li>
					<li>In the trial of a claim involving the fault of more than one party to the claim, including third-party defendants and persons who have been released pursuant to <span class="ref">section 668.7</span>, the court, unless otherwise agreed by all parties, shall instruct the jury to answer special interrogatories or, if there is no jury, shall make findings, indicating all of the following:</li>
				</ol>
				<div class="hover" id="rhov" style="left:300px;top:150px;width:360px">
					<span class="eyebrow">Iowa Code · 668.7 · currently effective</span>
					<div class="t">Effect of release</div>
					<div class="x">A release, covenant not to sue, covenant not to enforce judgment, or similar agreement entered into by a claimant and a person liable, discharges that person from all liability for contribution, but it does not discharge any other persons liable upon the same claim unless it so provides.</div>
					<div class="l">Open section 668.7 · Cited by 41 decisions</div>
				</div>
			</div>`;
		st.appendChild(main);
		const r = el("div", "r-rail");
		r.innerHTML = `
			<div class="fade" id="rr">
				<div class="tile"><div class="h">CITATION</div><div class="r">Iowa Code 668.3</div><div class="r blue">Official source — legis.iowa.gov ↗</div></div>
				<div class="tile"><div class="h">IN-TEXT CITATIONS</div><div class="r" id="rail668">section 668.7 <span class="st ok">Current</span></div><div class="r">section 624.18 <span class="st ok">Current</span></div><div class="r">ch 157</div><div class="r">ch 197</div></div>
				<div class="tile"><div class="h">IN THIS CHAPTER</div><div class="r">668.1<small>Fault defined</small></div><div class="r">668.2<small>Party defined</small></div><div class="r sel">668.3<small>Comparative fault — effect — payment method</small></div><div class="r">668.4<small>Joint and several liability</small></div></div>
			</div>`;
		st.appendChild(r);
	},
	steps: [
		[
			100,
			function () {
				this.moveTo("#rq", 40, 22);
			},
		],
		[
			300,
			function () {
				this.style("#rph", "display", "none");
				this.type("#rq", "668.3", 900);
			},
		],
		[
			1400,
			function () {
				this.show("#sug");
			},
		],
		[
			2100,
			function () {
				this.moveTo("#sug .s.hot", 120, 18);
			},
		],
		[
			2700,
			function () {
				this.click();
			},
		],
		[
			3000,
			function () {
				this.hide("#sug");
				this.text("#rq", "");
				this.style("#rph", "display", "");
				this.html(
					"#crumb",
					"Library &nbsp;/&nbsp; Iowa Code &nbsp;/&nbsp; Iowa Code 668 &nbsp;/&nbsp; <b>668.3</b>",
				);
				this.show("#rd");
				this.show("#rr");
				this.moveCursor(700, 620);
			},
		],
		[
			5600,
			function () {
				this.moveTo("#ref1", 30, 8);
			},
		],
		[
			6300,
			function () {
				this.addClass("#ref1", "hot");
				this.addClass("#rail668", "sel");
				this.hoverCard("#rhov", "#ref1", "#rd", -40);
			},
		],
		[
			8200,
			function () {
				this.hide("#rhov");
				this.removeClass("#ref1", "hot");
				this.removeClass("#rail668", "sel");
				this.moveTo("#cmpbtn", 40, 14);
			},
		],
		[
			8900,
			function () {
				this.click();
				this.addClass("#cmpbtn", "hot");
			},
		],
		[
			9200,
			function () {
				this.show("#cmpbadge");
				this.moveCursor(700, 620);
			},
		],
		[
			10000,
			function () {
				// PLACEHOLDER diff: illustrative words, not a real 2024→2025 change.
				const d = this.stage.querySelector<HTMLElement>("#d1");
				const i = this.stage.querySelector<HTMLElement>("#i1");
				if (!d || !i) return;
				d.className = "del";
				d.textContent = " or otherwise discharged";
				i.className = "ins";
				i.textContent = " pursuant to a covenant not to sue";
			},
		],
		[
			12000,
			function () {
				this.removeClass("#cmpbtn", "hot");
			},
		],
	],
};

// ---------------------------------------------------------------------------
// Search: one box → ranked across sources → facet click filters in place
// ---------------------------------------------------------------------------

const HITS: [title: string, meta: string, excerpt: string, kind: string][] = [
	[
		"Slager v. HWA Corp.",
		"435 N.W.2d 349 · Supreme Court of Iowa · 1989 · Cited by 31",
		"That theory is strict tort liability in products liability cases. Although section 668.1(1) uses the generic term “strict tort liability,” we think it includes products liability…",
		"sc",
	],
	[
		"Mulhern v. Catholic Health Initiatives",
		"799 N.W.2d 104 · Supreme Court of Iowa · 2011 · Cited by 29",
		"The majority’s holding that the negligence of the defendant may not be compared with the intentional conduct of the decedent … is inconsistent with the fundamental principle of <mark>comparative fault</mark> of linking liability with <mark>fault</mark>.",
		"sc",
	],
	[
		"Thomas v. Solberg",
		"442 N.W.2d 73 · Supreme Court of Iowa · 1989 · Cited by 10",
		"In a partial settlement of a <mark>comparative fault</mark> case with two of three defendants, the plaintiff received $75,000. The jury ultimately found that the settling defendants were liable for less…",
		"sc",
	],
	[
		"Rozevink v. Faris",
		"342 N.W.2d 845 · Court of Appeals of Iowa · 1983 · Cited by 8",
		"The trial court instructed the jury on <mark>comparative fault</mark> rather than contributory negligence…",
		"ca",
	],
	[
		"Iowa Code 668.3 — Comparative fault — effect — payment method",
		"Iowa Code · ch. 668 · effective Jan 1, 2025",
		"Contributory fault shall not bar recovery in an action by a claimant to recover damages for fault resulting in death or in injury to person or property unless the claimant bears a greater percentage of <mark>fault</mark>…",
		"code",
	],
];

export const search: Demo = {
	key: "search",
	stepCopy: [
		[
			"One box, every Iowa source.",
			"Cases, the Code, the Admin Code, Acts and Court Rules rank together, so you do not pick a database before you know the answer.",
		],
		[
			"Facets count the actual result set.",
			"Content type, court, status and year are computed from the hits, not the whole corpus. The numbers mean something.",
		],
		[
			"Refine without leaving the page.",
			"One click on a court or a status filters the list in place and the counts follow. Superseded and overruled authority is labelled in the list, not discovered later.",
		],
	],
	phases: [0, 3400, 8000],
	total: 12600,
	captions: [
		[0, "Typing “comparative fault”"],
		[2400, "Ranked across every source"],
		[3400, "Five sources, one list · counts from the hits"],
		[8000, "Filter to Supreme Court of Iowa"],
		[9600, "List and counts update in place"],
	],
	build(st) {
		st.appendChild(rail(0));
		const top = el("div", "topbar");
		top.innerHTML = `<span class="crumb">Library</span><div class="searchbox" style="max-width:640px">${searchIcon()}<span class="q" id="sq"></span><span class="caret"></span><span id="sph" style="margin-left:6px">Search Iowa law…</span><span class="kbd">⌘K</span></div>`;
		st.appendChild(top);
		const m = el("div", "s-main");
		m.innerHTML = `
			<div class="fade" id="sres">
				<h2>Results for “comparative fault” <small id="scount">Top 50 results · showing 1–10</small> <span class="mode">Natural language</span> <small style="color:#0f62fe">Search as terms &amp; connectors</small></h2>
				<div class="s-grid">
					<div class="facets">
						<div class="g"><span class="eyebrow">Content type</span>
							<div class="f on">All content <span class="c" id="fc0">0</span></div>
							<div class="f">Cases <span class="c" id="fc1">0</span></div>
							<div class="f">Iowa Code <span class="c" id="fc2">0</span></div>
							<div class="f">Iowa Admin. Code <span class="c">2</span></div>
							<div class="f">Court Rules <span class="c">1</span></div>
						</div>
						<div class="g"><span class="eyebrow">Court</span>
							<div class="f on" id="fany">Any court</div>
							<div class="f" id="fsc">Supreme Court of Iowa <span class="c" id="fc3">0</span></div>
							<div class="f" id="fca">Court of Appeals of Iowa <span class="c" id="fc4">0</span></div>
						</div>
						<div class="g"><span class="eyebrow">Status</span>
							<div class="f on">Any status</div>
							<div class="f">Good law <span class="c">44</span></div>
							<div class="f">Questioned <span class="c">4</span></div>
							<div class="f">Overruled <span class="c">2</span></div>
						</div>
					</div>
					<div class="results">
						<div class="sort">Sort <b>Relevance ▾</b></div>
						${HITS.map(
							(h, i) =>
								`<div class="hit" data-k="${h[3]}" id="h${i}"><div class="k"><b>${h[3] === "code" ? "Statute" : "Case"}</b>${h[3] === "code" ? "Iowa Code" : "Opinion"}${i === 3 ? '<span class="st warn" style="padding:0 6px;font-size:11px">Questioned</span>' : ""}</div><div class="t">${h[0]}</div><div class="m">${h[1]}</div><div class="x">${h[2]}</div></div>`,
						).join("")}
					</div>
				</div>
			</div>`;
		st.appendChild(m);
	},
	steps: [
		[
			100,
			function () {
				this.moveTo("#sq", 40, 22);
			},
		],
		[
			300,
			function () {
				this.style("#sph", "display", "none");
				this.type("#sq", "comparative fault", 1600);
			},
		],
		[
			2400,
			function () {
				this.moveCursor(900, 640);
			},
		],
		[
			3400,
			function () {
				this.show("#sres");
				const n = (v: number) => String(v);
				this.count("#fc0", 50, 1200, n);
				this.count("#fc1", 41, 1200, n);
				this.count("#fc2", 6, 1200, n);
				this.count("#fc3", 33, 1200, n);
				this.count("#fc4", 8, 1200, n);
			},
		],
		[
			3500,
			function () {
				this.show("#h0");
			},
		],
		[
			3750,
			function () {
				this.show("#h1");
			},
		],
		[
			4000,
			function () {
				this.show("#h2");
			},
		],
		[
			4250,
			function () {
				this.show("#h3");
			},
		],
		[
			4500,
			function () {
				this.show("#h4");
			},
		],
		[
			8000,
			function () {
				this.moveTo("#fsc", 80, 14);
			},
		],
		[
			8600,
			function () {
				this.addClass("#fsc", "hot");
			},
		],
		[
			9000,
			function () {
				this.click();
				this.removeClass("#fsc", "hot");
				this.addClass("#fsc", "on");
				this.removeClass("#fany", "on");
			},
		],
		[
			9300,
			function () {
				this.addClass('.hit:not([data-k="sc"])', "gone");
				this.text("#fc0", "33");
				this.text("#fc1", "33");
				this.text("#fc2", "0");
				this.text("#fc4", "0");
				this.text("#scount", "33 results · showing 1–10");
			},
		],
		[
			10200,
			function () {
				this.moveCursor(900, 640);
			},
		],
	],
};

export const DEMOS = { assistant, reader, search } as const;
export type DemoKey = keyof typeof DEMOS;
