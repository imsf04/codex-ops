#!/usr/bin/env node
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { parse } from 'yaml'
import assert from 'node:assert/strict'

// Read only the committed source set; legacy local workflows may still be present.
const files = execFileSync('git', ['ls-files', '.github/workflows'], { encoding: 'utf8' }).trim().split('\n')
assert.deepEqual(files, ['.github/workflows/ci.yml'])
const workflow = parse(readFileSync(files[0], 'utf8'))
for (const event of ['push', 'pull_request', 'merge_group']) {
  assert.ok(Object.hasOwn(workflow.on, event), `Missing ${event} trigger`)
  assert.equal(workflow.on[event], null, `Filtered ${event} can bypass validation`)
}
assert.equal(workflow.permissions.contents, 'read')
const jobs = workflow.jobs
for (const [id, job] of Object.entries(jobs)) {
  assert.ok(job['runs-on'], `${id} needs a runner`)
  assert.ok(job['timeout-minutes'] > 0, `${id} needs a timeout`)
  assert.ok(!job['continue-on-error'], `${id} must block on failure`)
  for (const step of job.steps ?? []) assert.ok(!step['continue-on-error'], `${id} ignores a step failure`)
}
assert.deepEqual(jobs.dependencies.strategy.matrix.os,
  ['windows-latest', 'ubuntu-24.04', 'macos-latest', 'macos-15-intel'])
assert.ok(jobs.dependencies.steps.some(step => step.run === 'uv run --locked python -m unittest discover -s tests' && !step.if),
  'Every platform must run the full suite')
assert.ok(jobs.dependencies.steps.some(step => step.run?.includes('tests/check_portable_bundle.py') && !step.if),
  'Every platform must verify installation')
const required = jobs['ci-required']
assert.equal(required.name, 'CI required')
assert.equal(required.if, 'always()')
assert.deepEqual([...required.needs].sort(), Object.keys(jobs).filter(id => id !== 'ci-required').sort())
assert.equal(jobs['windows-required'].name, 'Codex Ops Windows')
assert.deepEqual(jobs['windows-required'].needs, ['dependencies'])
console.log('Workflow contracts passed: four mandatory platforms, full suites, installation and protected check names.')
