/**
 * Friendly names for the generated API types. Never hand-write API shapes: everything here is an
 * alias of `schema.d.ts`, regenerated from the FastAPI OpenAPI document with `make openapi`.
 */
import type { components } from '@/api/schema';

type S = components['schemas'];

export type AppealContent = S['AppealContent'];
export type AppealEdit = S['AppealEdit'];
export type AppealForum = S['AppealForum'];
export type AppealItem = S['AppealItem'];
export type AppealStatus = S['AppealStatus'];
export type AppealSummary = S['AppealSummary'];
export type AppealVersion = S['AppealVersion'];
export type AuditLogEntry = S['AuditLogEntry'];
export type AuditResult = S['AuditResult'];
export type AuditRun = S['AuditRun'];
export type BillLine = S['BillLine'];
export type ClaimFacts = S['ClaimFacts'];
export type ClaimList = S['ClaimList'];
export type ClaimMode = S['ClaimMode'];
export type ClaimRecord = S['ClaimRecord'];
export type ClaimStatus = S['ClaimStatus'];
export type ClaimSummary = S['ClaimSummary'];
export type DemoClaim = S['DemoClaim'];
export type DocType = S['DocType'];
export type DocumentOut = S['DocumentOut'];
export type Flag = S['Flag'];
export type FlagNarrative = S['FlagNarrative'];
export type FlagReview = S['FlagReview'];
export type ForumOption = S['ForumOption'];
export type GroComplaint = S['GroComplaint'];
export type LineCategory = S['LineCategory'];
export type LineCorrection = S['LineCorrection'];
export type LineOutcome = S['LineOutcome'];
export type Policy = S['Policy'];
export type PolicyClause = S['PolicyClause'];
export type PolicyTermNote = S['PolicyTermNote'];
export type Prose = S['Prose'];
export type ReasoningStatus = S['ReasoningStatus'];
export type ReviewIssue = S['ReviewIssue'];
export type RuleCitation = S['RuleCitation'];
export type RunEvent = S['RunEvent'];
export type Severity = S['Severity'];
export type SignRequest = S['SignRequest'];
export type Totals = S['Totals'];
export type TraceStep = S['TraceStep'];
export type Workspace = S['Workspace'];
