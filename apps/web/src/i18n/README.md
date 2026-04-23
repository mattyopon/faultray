# i18n dictionary split plan (#35)

Current state: `src/i18n/app-dict.ts` holds **8177 lines / ~450KB** in a
single module with **8 locales × 24 sections** all flattened. This defeats
code-splitting — every page ships every locale in its initial bundle.

## Target layout (progressive)

```
src/i18n/
├── README.md                (this file)
├── app-dict.ts              (legacy re-export shim; kept until all
│                             callers migrate to `getDict(locale, section)`)
├── types.ts                 (exported LocaleDict shape)
├── dict/
│   ├── en.ts                (all 24 sections for English)
│   ├── ja.ts
│   ├── de.ts
│   ├── fr.ts
│   ├── es.ts
│   ├── zh.ts
│   ├── ko.ts
│   └── pt.ts
└── loader.ts                (lazy-load entry: getDict(locale, section))
```

## API contract (proposed)

```ts
// Server or static paths — tree-shaken
import { dict as enDict } from "@/i18n/dict/en";
use(enDict.pricing);

// Dynamic / SSR paths
import { getDict } from "@/i18n/loader";
const pricing = await getDict(locale, "pricing");
```

## Why not a single sweep PR

8 locales × 24 sections × existing 20+ callers means the cutover churns
~200 imports. Doing this in one PR maximises merge-conflict risk with
any in-flight feature work. The plan is:

1. **[done] This PR**: add `src/i18n/README.md` + `src/i18n/types.ts`
   + empty `src/i18n/dict/` scaffolding. No behavior change.
2. **Next PR per locale**: extract each locale from `app-dict.ts` into
   `dict/<locale>.ts`, retain `app-dict.ts` re-export so callers keep
   working.
3. **Flip-over PR**: migrate all callers to `getDict(...)`, delete
   `app-dict.ts`.

## Measured target

Baseline: `/dashboard` initial JS payload includes the full ~450KB
dictionary. After migration: only the requested locale's 24 sections
should land in the bundle (~60KB). Tracked via Next.js build analyzer
in a follow-up PR.
