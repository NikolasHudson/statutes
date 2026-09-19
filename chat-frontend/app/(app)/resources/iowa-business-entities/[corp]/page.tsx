"use client";

// One business entity, as the Secretary of State publishes it.
//
// Everything on this page is a record, never authority: the header links out
// to the official SOS search, and the provenance strip says what day the data
// is from. The registered-agent block is the reason this page exists for a
// lawyer — who to serve, and what else that agent is on.

import { ArrowLeftIcon, ExternalLinkIcon } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
	KVList,
	Notification,
	Panel,
	Tag,
} from "@/components/carbon/primitives";
import {
	EntityTable,
	ProvenanceStrip,
	StatusPill,
} from "@/components/resources/provenance";
import {
	agentEntities,
	type EntityAddress,
	type EntityDetail,
	type EntitySearchResponse,
	fmtDate,
	getEntity,
	ResourcesError,
	SOS_OFFICIAL_SEARCH,
} from "@/lib/iowa-resources";

function addressLines(address: EntityAddress): string[] {
	const street = [address.address_1, address.address_2].filter(Boolean);
	const locality = [
		[address.city, address.state].filter(Boolean).join(", "),
		address.zip,
	]
		.filter(Boolean)
		.join(" ");
	return [...street, locality, address.country ?? ""].filter(Boolean);
}

function AddressPanel({
	title,
	name,
	address,
	nameLabel,
}: {
	title: string;
	name: string;
	address: EntityAddress;
	nameLabel: string;
}) {
	const lines = addressLines(address);
	return (
		<Panel title={title}>
			<div className="p-4 text-sm">
				<p className="text-[var(--cds-helper)] text-xs">{nameLabel}</p>
				<p className="mt-1 font-medium">{name || "Not listed"}</p>
				{lines.length > 0 ? (
					<address className="mt-3 text-[var(--cds-text-2)] not-italic leading-relaxed">
						{lines.map((line) => (
							<span className="block" key={line}>
								{line}
							</span>
						))}
					</address>
				) : (
					<p className="mt-3 text-[var(--cds-text-2)]">No address listed.</p>
				)}
			</div>
		</Panel>
	);
}

export default function BusinessEntityDetailPage() {
	const params = useParams<{ corp: string }>();
	const corp = params?.corp ?? "";

	const [entity, setEntity] = useState<EntityDetail | null>(null);
	const [error, setError] = useState<Error | null>(null);
	const [agentRows, setAgentRows] = useState<EntitySearchResponse | null>(null);

	useEffect(() => {
		if (!corp) return;
		const controller = new AbortController();
		setEntity(null);
		setError(null);
		setAgentRows(null);
		getEntity(corp, controller.signal)
			.then(setEntity)
			.catch((e) => {
				if (controller.signal.aborted) return;
				setError(e as Error);
			});
		return () => controller.abort();
	}, [corp]);

	// The reverse lookup is a second call so the detail view paints immediately
	// and a slow agent query never holds up the record itself.
	useEffect(() => {
		if (!entity?.registered_agent || entity.agent_entity_count === 0) return;
		const controller = new AbortController();
		agentEntities(
			entity.registered_agent,
			entity.registered_agent_address.zip,
			1,
			controller.signal,
		)
			.then(setAgentRows)
			.catch(() => undefined);
		return () => controller.abort();
	}, [entity]);

	if (error) {
		const status = error instanceof ResourcesError ? error.status : 0;
		return (
			<div className="px-5 py-10 sm:px-8 lg:py-14">
				<Notification
					className="max-w-2xl"
					kind={status === 402 ? "warning" : "error"}
					title={
						status === 404
							? "No such entity"
							: status === 402
								? "Resources needs an active plan"
								: "Could not load this entity"
					}
				>
					{error.message}
				</Notification>
				<Link
					className="mt-6 inline-flex items-center gap-2 text-[var(--cds-link)] text-sm hover:underline"
					href="/resources/iowa-business-entities"
				>
					<ArrowLeftIcon className="size-4" />
					Back to search
				</Link>
			</div>
		);
	}

	if (!entity) {
		return (
			<div className="px-5 py-10 text-[var(--cds-text-2)] text-sm sm:px-8">
				Loading…
			</div>
		);
	}

	return (
		<div className="px-5 py-10 sm:px-8 lg:py-14">
			<Link
				className="inline-flex items-center gap-2 text-[var(--cds-link)] text-sm hover:underline"
				href="/resources/iowa-business-entities"
			>
				<ArrowLeftIcon className="size-4" />
				Iowa business entities
			</Link>

			<header className="mt-6">
				<div className="flex flex-wrap items-center gap-3">
					<StatusPill
						isActive={entity.is_active}
						deactivatedOn={entity.deactivated_on}
					/>
					<Tag kind="outline">No. {entity.corp_number}</Tag>
				</div>
				<h1 className="mt-4 max-w-4xl font-light text-3xl sm:text-4xl">
					{entity.legal_name}
				</h1>
				<p className="mt-3 text-[15px] text-[var(--cds-text-2)]">
					{entity.entity_type}
					{entity.effective_date
						? ` · Effective ${fmtDate(entity.effective_date)}`
						: ""}
				</p>
				<a
					className="mt-4 inline-flex items-center gap-2 text-[var(--cds-link)] text-sm hover:underline"
					href={SOS_OFFICIAL_SEARCH}
					target="_blank"
					rel="noreferrer"
				>
					Verify on the Secretary of State’s own search
					<ExternalLinkIcon className="size-3.5" />
				</a>
			</header>

			<div className="mt-10 grid max-w-5xl gap-5 lg:grid-cols-2">
				<AddressPanel
					title="Registered agent"
					nameLabel="Agent"
					name={entity.registered_agent}
					address={entity.registered_agent_address}
				/>
				<AddressPanel
					title="Principal office"
					nameLabel="Office"
					name={entity.home_office}
					address={entity.home_office_address}
				/>
			</div>

			<div className="mt-5 max-w-5xl lg:max-w-xl">
				<Panel title="Record">
					<KVList
						rows={[
							["Corporation number", entity.corp_number],
							["Entity type", entity.entity_type || "—"],
							[
								"Effective date",
								entity.effective_date ? fmtDate(entity.effective_date) : "—",
							],
							["First seen in this data", fmtDate(entity.first_seen)],
							["Last seen in this data", fmtDate(entity.last_seen)],
						]}
					/>
				</Panel>
			</div>

			{entity.agent_entity_count > 0 && (
				<section className="mt-10 max-w-5xl">
					<Panel
						title={`Other entities with this registered agent (${entity.agent_entity_count.toLocaleString("en-US")})`}
					>
						{agentRows === null ? (
							<p className="px-4 py-6 text-[var(--cds-text-2)] text-sm">
								Loading…
							</p>
						) : (
							<EntityTable
								rows={agentRows.results.filter(
									(r) => r.corp_number !== entity.corp_number,
								)}
								emptyLabel="No other entities found for this agent."
							/>
						)}
					</Panel>
					<p className="mt-3 text-[var(--cds-helper)] text-xs">
						Matched on the agent’s name and ZIP, which is a good guess and not a
						guarantee — two people with the same name in the same ZIP would be
						listed together.
					</p>
				</section>
			)}

			<div className="mt-10 max-w-3xl">
				<ProvenanceStrip asOf={entity.as_of} />
			</div>
		</div>
	);
}
