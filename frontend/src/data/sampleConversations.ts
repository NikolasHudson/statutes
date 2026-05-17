import type { Conversation } from '../types';

export const sampleConversations: Conversation[] = [
  {
    id: 'c1',
    title: 'Habitable premises — landlord duties',
    updatedAt: new Date(Date.now() - 1000 * 60 * 12).toISOString(),
    pinned: true,
    messages: [
      {
        id: 'm1',
        role: 'user',
        content:
          'What Iowa statutes require a landlord to maintain habitable premises, and what remedies does the tenant have if they refuse?',
        createdAt: new Date(Date.now() - 1000 * 60 * 14).toISOString(),
      },
      {
        id: 'm2',
        role: 'assistant',
        createdAt: new Date(Date.now() - 1000 * 60 * 13).toISOString(),
        content:
          "Under Iowa's Uniform Residential Landlord and Tenant Act, the controlling provision is **Iowa Code § 562A.15**, which obligates a landlord to keep the premises in a fit and habitable condition — the statute uses the word *fit*, but courts read it as Iowa's version of the implied warranty of habitability.\n\nIf a landlord materially fails to comply, the tenant's remedies are spelled out in **§ 562A.21** (rent abatement, repair-and-deduct in limited cases, and termination after written notice). Where the noncompliance is willful, **§ 562A.21(3)** allows the tenant to recover actual damages plus reasonable attorney fees.\n\nAlways check the *effective date* — § 562A.15 was last touched by 2018 Iowa Acts ch. 1056.",
        citations: [
          {
            id: 'cit1',
            citation: 'Iowa Code § 562A.15',
            heading: 'Landlord to maintain fit premises',
            source: 'Iowa Code',
            url: 'https://www.legis.iowa.gov/docs/code/562A.15.pdf',
            effectiveFrom: '2018-07-01',
            enactedBy: '2018 Iowa Acts ch. 1056',
            snippet:
              'A landlord shall … make all repairs and do whatever is necessary to put and keep the premises in a fit and habitable condition.',
            relevance: 0.96,
          },
          {
            id: 'cit2',
            citation: 'Iowa Code § 562A.21',
            heading: 'Noncompliance by the landlord',
            source: 'Iowa Code',
            url: 'https://www.legis.iowa.gov/docs/code/562A.21.pdf',
            effectiveFrom: '2018-07-01',
            relevance: 0.88,
          },
        ],
      },
    ],
  },
  {
    id: 'c2',
    title: 'OWI 1st offense — sentencing',
    updatedAt: new Date(Date.now() - 1000 * 60 * 60 * 6).toISOString(),
    messages: [],
  },
  {
    id: 'c3',
    title: 'Foreign farmland ownership (ch. 9H)',
    updatedAt: new Date(Date.now() - 1000 * 60 * 60 * 28).toISOString(),
    messages: [],
  },
  {
    id: 'c4',
    title: 'R. Civ. P. 1.943 voluntary dismissal',
    updatedAt: new Date(Date.now() - 1000 * 60 * 60 * 24 * 3).toISOString(),
    messages: [],
  },
  {
    id: 'c5',
    title: 'Dissolution of marriage residency',
    updatedAt: new Date(Date.now() - 1000 * 60 * 60 * 24 * 9).toISOString(),
    messages: [],
  },
];
