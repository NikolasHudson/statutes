export type Suggestion = {
  icon: 'gavel' | 'home' | 'family' | 'business' | 'criminal' | 'rules';
  title: string;
  prompt: string;
};

export const suggestions: Suggestion[] = [
  {
    icon: 'home',
    title: 'Landlord–tenant',
    prompt:
      'What Iowa statutes require a landlord to maintain habitable premises, and what remedies does the tenant have?',
  },
  {
    icon: 'gavel',
    title: 'Pinpoint citation',
    prompt: 'Pull the current text of Iowa Code § 714.16(2)(a) and tell me when it was last amended.',
  },
  {
    icon: 'family',
    title: 'Family law',
    prompt:
      'Summarize Iowa Code chapter 598 on dissolution of marriage — grounds, residency, and waiting periods.',
  },
  {
    icon: 'rules',
    title: 'Court rules',
    prompt: 'What does Iowa R. Civ. P. 1.943 say about voluntary dismissal, and how have courts applied it?',
  },
  {
    icon: 'business',
    title: 'Business / agribusiness',
    prompt:
      'What disclosures does Iowa Code chapter 9H require for foreign corporate ownership of farmland?',
  },
  {
    icon: 'criminal',
    title: 'Criminal defense',
    prompt:
      'What are the elements and sentencing range for OWI 1st offense under Iowa Code § 321J.2?',
  },
];
