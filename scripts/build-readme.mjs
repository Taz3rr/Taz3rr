// Builds README.md from README.template.md in one season's colours.
// Colours come from the portfolio's season themes (src/styles/base.css).
//
//   node scripts/build-readme.mjs          -> season for the current month
//   node scripts/build-readme.mjs fall     -> force a season (night | fall | winter | spring)

import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const SEASONS = {
  night: {
    season: 'Night', hint: 'navy, black and white',
    bg: '04060d', fg: 'e9ecf4', mute: '8a95b3', dim: '4a5576', accent: '4a70e6',
    badge: '0a1330', badgeInk: 'e9ecf4',
    g1: '04060d', g2: '0a1330', g3: '1b3270',
  },
  fall: {
    season: 'Fall', hint: 'autumn',
    bg: 'f6e7ce', fg: '3f2a1d', mute: '6b4423', dim: 'a8835f', accent: 'c65d32',
    badge: '9e3f2d', badgeInk: 'f6e7ce',
    g1: 'f6e7ce', g2: 'd99a4e', g3: 'c65d32',
  },
  winter: {
    season: 'Winter', hint: 'snow',
    bg: 'f7fbff', fg: '2b404c', mute: '4f6a7a', dim: '94adbc', accent: '4d7590',
    badge: '435d6b', badgeInk: 'f7fbff',
    g1: 'f7fbff', g2: 'c9dfec', g3: '708fa3',
  },
  spring: {
    season: 'Spring', hint: 'bloom',
    bg: 'fff9ee', fg: '2e3b2b', mute: '56664f', dim: 'a1b199', accent: 'c4547f',
    badge: 'c4547f', badgeInk: 'fff9ee',
    g1: 'fff9ee', g2: 'f5c2d7', g3: 'a8d5a2',
  },
}

// Dec–Feb winter, Mar–May spring, Jun–Aug night, Sep–Nov fall.
const BY_MONTH = ['winter', 'winter', 'spring', 'spring', 'spring', 'night',
  'night', 'night', 'fall', 'fall', 'fall', 'winter']

const arg = (process.argv[2] || 'auto').toLowerCase()
const id = arg === 'auto' ? BY_MONTH[new Date().getUTCMonth()] : arg
const theme = SEASONS[id]
if (!theme) {
  console.error(`Unknown season "${arg}". Use auto, ${Object.keys(SEASONS).join(', ')}.`)
  process.exit(1)
}

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const template = readFileSync(join(root, 'README.template.md'), 'utf8')
const out = template.replace(/\{\{(\w+)\}\}/g, (m, key) => {
  if (!(key in theme)) throw new Error(`Template uses {{${key}}}, but no season defines it.`)
  return theme[key]
})

writeFileSync(join(root, 'README.md'), out)
console.log(`README.md built in ${theme.season}.`)
