# =============================================================================
# SessionState FlatBuffer Generated Types - Complete Exports
# =============================================================================
# Exports all generated FlatBuffer type classes AND builder functions.
# =============================================================================

# -----------------------------------------------------------------------------
# AffectiveNowSection - Type + Builder Functions
# -----------------------------------------------------------------------------
from .AffectiveNowSection import (
    AffectiveNowSection,
    AffectiveNowSectionAddCelebrationAppropriate,
    AffectiveNowSectionAddConfidence,
    AffectiveNowSectionAddCurrentEmotion,
    AffectiveNowSectionAddDimensions,
    AffectiveNowSectionAddEmpathyNeeded,
    AffectiveNowSectionAddHeader,
    AffectiveNowSectionAddIntensity,
    AffectiveNowSectionAddLastSignificantChangeMs,
    AffectiveNowSectionAddLastUpdatedMs,
    AffectiveNowSectionAddRecentEmotions,
    AffectiveNowSectionAddSource,
    AffectiveNowSectionAddTrajectory,
    AffectiveNowSectionEnd,
    AffectiveNowSectionStart,
    AffectiveNowSectionStartRecentEmotionsVector,
)

# -----------------------------------------------------------------------------
# AgentLease - Type + Builder Functions
# -----------------------------------------------------------------------------
from .AgentLease import (
    AgentLease,
    AgentLeaseAddAgentId,
    AgentLeaseAddAgentType,
    AgentLeaseAddCapabilities,
    AgentLeaseAddLeaseExpiresMs,
    AgentLeaseAddLeaseStartedMs,
    AgentLeaseAddPriority,
    AgentLeaseAddState,
    AgentLeaseEnd,
    AgentLeaseStart,
    AgentLeaseStartCapabilitiesVector,
)

# -----------------------------------------------------------------------------
# AgentState - Enum
# -----------------------------------------------------------------------------
from .AgentState import AgentState

# -----------------------------------------------------------------------------
# ArchivedFact - Type + Builder Functions
# -----------------------------------------------------------------------------
from .ArchivedFact import (
    ArchivedFact,
    ArchivedFactAddAccessCount,
    ArchivedFactAddDemotedAt,
    ArchivedFactAddFact,
    ArchivedFactAddIsStale,
    ArchivedFactAddLastAccessedTurn,
    ArchivedFactAddLruScore,
    ArchivedFactAddOriginalTurn,
    ArchivedFactEnd,
    ArchivedFactStart,
)

# -----------------------------------------------------------------------------
# BeliefsActiveSection - Type + Builder Functions
# -----------------------------------------------------------------------------
from .BeliefsActiveSection import (
    BeliefsActiveSection,
    BeliefsActiveSectionAddCurrentTurnFacts,
    BeliefsActiveSectionAddEntityCount,
    BeliefsActiveSectionAddFactCount,
    BeliefsActiveSectionAddHeader,
    BeliefsActiveSectionAddLastUpdatedMs,
    BeliefsActiveSectionAddMentionedEntities,
    BeliefsActiveSectionAddMentionedLocation,
    BeliefsActiveSectionAddMentionedTime,
    BeliefsActiveSectionAddPinnedFactIds,
    BeliefsActiveSectionAddTurnId,
    BeliefsActiveSectionEnd,
    BeliefsActiveSectionStart,
    BeliefsActiveSectionStartCurrentTurnFactsVector,
    BeliefsActiveSectionStartMentionedEntitiesVector,
    BeliefsActiveSectionStartPinnedFactIdsVector,
)

# -----------------------------------------------------------------------------
# BeliefsHistorySection - Type + Builder Functions
# -----------------------------------------------------------------------------
from .BeliefsHistorySection import (
    BeliefsHistorySection,
    BeliefsHistorySectionAddArchivedCount,
    BeliefsHistorySectionAddArchivePointer,
    BeliefsHistorySectionAddEntityIndex,
    BeliefsHistorySectionAddEvictionThreshold,
    BeliefsHistorySectionAddFacts,
    BeliefsHistorySectionAddHeader,
    BeliefsHistorySectionAddMaxFacts,
    BeliefsHistorySectionAddNewestTurn,
    BeliefsHistorySectionAddNextEvictionCandidates,
    BeliefsHistorySectionAddOldestTurn,
    BeliefsHistorySectionAddTotalFacts,
    BeliefsHistorySectionEnd,
    BeliefsHistorySectionStart,
    BeliefsHistorySectionStartEntityIndexVector,
    BeliefsHistorySectionStartFactsVector,
    BeliefsHistorySectionStartNextEvictionCandidatesVector,
)

# -----------------------------------------------------------------------------
# Clarification - Type + Builder Functions
# -----------------------------------------------------------------------------
from .Clarification import (
    Clarification,
    ClarificationAddAgentId,
    ClarificationAddAnswer,
    ClarificationAddAnsweredAtMs,
    ClarificationAddCreatedAtMs,
    ClarificationAddId,
    ClarificationAddOptions,
    ClarificationAddPriority,
    ClarificationAddQuestion,
    ClarificationAddRelatedEntity,
    ClarificationAddRelatedIntent,
    ClarificationAddSelectedOptionId,
    ClarificationAddStatus,
    ClarificationAddTimeoutMs,
    ClarificationEnd,
    ClarificationStart,
    ClarificationStartOptionsVector,
)

# -----------------------------------------------------------------------------
# ClarificationOption - Type + Builder Functions
# -----------------------------------------------------------------------------
from .ClarificationOption import (
    ClarificationOption,
    ClarificationOptionAddAction,
    ClarificationOptionAddConfidence,
    ClarificationOptionAddId,
    ClarificationOptionAddText,
    ClarificationOptionEnd,
    ClarificationOptionStart,
)

# -----------------------------------------------------------------------------
# ClarificationsSection - Type + Builder Functions
# -----------------------------------------------------------------------------
from .ClarificationsSection import (
    ClarificationsSection,
    ClarificationsSectionAddAvgResolutionTimeMs,
    ClarificationsSectionAddBlockingClarificationId,
    ClarificationsSectionAddHeader,
    ClarificationsSectionAddIsBlocked,
    ClarificationsSectionAddPending,
    ClarificationsSectionAddRecentlyResolved,
    ClarificationsSectionAddTotalPending,
    ClarificationsSectionAddTotalResolvedSession,
    ClarificationsSectionEnd,
    ClarificationsSectionStart,
    ClarificationsSectionStartPendingVector,
    ClarificationsSectionStartRecentlyResolvedVector,
)

# -----------------------------------------------------------------------------
# CompressedTurn - Type + Builder Functions
# -----------------------------------------------------------------------------
from .CompressedTurn import (
    CompressedTurn,
    CompressedTurnAddArchivedToLocalCold,
    CompressedTurnAddArchiveId,
    CompressedTurnAddEmotion,
    CompressedTurnAddEntities,
    CompressedTurnAddIntents,
    CompressedTurnAddKeyPhrases,
    CompressedTurnAddResponseTokens,
    CompressedTurnAddTimestampMs,
    CompressedTurnAddTurnId,
    CompressedTurnAddTurnNumber,
    CompressedTurnAddUserTokens,
    CompressedTurnEnd,
    CompressedTurnStart,
    CompressedTurnStartEntitiesVector,
    CompressedTurnStartIntentsVector,
    CompressedTurnStartKeyPhrasesVector,
)

# -----------------------------------------------------------------------------
# ControlSection - Type + Builder Functions
# -----------------------------------------------------------------------------
from .ControlSection import (
    ControlSection,
    ControlSectionAddAgentLeases,
    ControlSectionAddDomains,
    ControlSectionAddFlowState,
    ControlSectionAddHeader,
    ControlSectionAddIntents,
    ControlSectionAddNeverEvict,
    ControlSectionAddSafety,
    ControlSectionAddTurnLock,
    ControlSectionEnd,
    ControlSectionStart,
    ControlSectionStartAgentLeasesVector,
)

# -----------------------------------------------------------------------------
# ConversationThread - Type + Builder Functions
# -----------------------------------------------------------------------------
from .ConversationThread import (
    ConversationThread,
    ConversationThreadAddContextSummary,
    ConversationThreadAddGoal,
    ConversationThreadAddId,
    ConversationThreadAddIsGoalMet,
    ConversationThreadAddLastActiveTurn,
    ConversationThreadAddRelatedEntities,
    ConversationThreadAddRelatedIntents,
    ConversationThreadAddResolvedTurn,
    ConversationThreadAddResumptionHint,
    ConversationThreadAddStartedTurn,
    ConversationThreadAddState,
    ConversationThreadAddTitle,
    ConversationThreadEnd,
    ConversationThreadStart,
    ConversationThreadStartRelatedEntitiesVector,
    ConversationThreadStartRelatedIntentsVector,
)

# -----------------------------------------------------------------------------
# CostMetrics - Type + Builder Functions
# -----------------------------------------------------------------------------
from .CostMetrics import (
    CostMetrics,
    CostMetricsAddAvgCostPerTurn,
    CostMetricsAddEmbeddingCost,
    CostMetricsAddGenerationCost,
    CostMetricsAddReasoningCost,
    CostMetricsAddToolCost,
    CostMetricsAddTotalCostMicrodollars,
    CostMetricsEnd,
    CostMetricsStart,
)

# -----------------------------------------------------------------------------
# DomainContext - Type + Builder Functions
# -----------------------------------------------------------------------------
from .DomainContext import (
    DomainContext,
    DomainContextAddActiveDomains,
    DomainContextAddPrimaryDomain,
    DomainContextEnd,
    DomainContextStart,
    DomainContextStartActiveDomainsVector,
)

# -----------------------------------------------------------------------------
# EmotionDimensions - Type + Builder Functions
# -----------------------------------------------------------------------------
from .EmotionDimensions import (
    EmotionDimensions,
    EmotionDimensionsAddArousal,
    EmotionDimensionsAddDominance,
    EmotionDimensionsAddValence,
    EmotionDimensionsEnd,
    EmotionDimensionsStart,
)

# -----------------------------------------------------------------------------
# EmotionSnapshot - Type + Builder Functions
# -----------------------------------------------------------------------------
from .EmotionSnapshot import (
    EmotionSnapshot,
    EmotionSnapshotAddArousal,
    EmotionSnapshotAddEmotion,
    EmotionSnapshotAddIntensity,
    EmotionSnapshotAddTimestampMs,
    EmotionSnapshotAddTurnNumber,
    EmotionSnapshotAddValence,
    EmotionSnapshotEnd,
    EmotionSnapshotStart,
)

# -----------------------------------------------------------------------------
# EmotionTrajectory - Enum
# -----------------------------------------------------------------------------
from .EmotionTrajectory import EmotionTrajectory

# -----------------------------------------------------------------------------
# EntityFactIndex - Type + Builder Functions
# -----------------------------------------------------------------------------
from .EntityFactIndex import (
    EntityFactIndex,
    EntityFactIndexAddEntityId,
    EntityFactIndexAddFactIndices,
    EntityFactIndexAddLastUpdatedTurn,
    EntityFactIndexEnd,
    EntityFactIndexStart,
    EntityFactIndexStartFactIndicesVector,
)

# -----------------------------------------------------------------------------
# EntityRef - Type + Builder Functions
# -----------------------------------------------------------------------------
from .EntityRef import (
    EntityRef,
    EntityRefAddConfidence,
    EntityRefAddDisplayName,
    EntityRefAddId,
    EntityRefAddType,
    EntityRefEnd,
    EntityRefStart,
)

# -----------------------------------------------------------------------------
# ErrorMetrics - Type + Builder Functions
# -----------------------------------------------------------------------------
from .ErrorMetrics import (
    ErrorMetrics,
    ErrorMetricsAddErrorRate,
    ErrorMetricsAddLastErrorMessage,
    ErrorMetricsAddLastErrorTurn,
    ErrorMetricsAddModelErrors,
    ErrorMetricsAddRateLimitErrors,
    ErrorMetricsAddTimeoutErrors,
    ErrorMetricsAddToolErrors,
    ErrorMetricsAddTotalErrors,
    ErrorMetricsAddValidationErrors,
    ErrorMetricsEnd,
    ErrorMetricsStart,
)

# -----------------------------------------------------------------------------
# Fact - Type + Builder Functions
# -----------------------------------------------------------------------------
from .Fact import (
    Fact,
    FactAddConfidence,
    FactAddId,
    FactAddObject,
    FactAddPredicate,
    FactAddPrivacyBand,
    FactAddSource,
    FactAddSubject,
    FactAddTimestampMs,
    FactEnd,
    FactStart,
)

# -----------------------------------------------------------------------------
# FlowPhase - Enum
# -----------------------------------------------------------------------------
from .FlowPhase import FlowPhase

# -----------------------------------------------------------------------------
# FlowState - Type + Builder Functions
# -----------------------------------------------------------------------------
from .FlowState import (
    FlowState,
    FlowStateAddCompletedAgents,
    FlowStateAddCurrentPhase,
    FlowStateAddPendingAgents,
    FlowStateAddStartedAtMs,
    FlowStateAddTimeoutMs,
    FlowStateAddTurnId,
    FlowStateEnd,
    FlowStateStart,
    FlowStateStartCompletedAgentsVector,
    FlowStateStartPendingAgentsVector,
)

# -----------------------------------------------------------------------------
# HistoryActiveSection - Type + Builder Functions
# -----------------------------------------------------------------------------
from .HistoryActiveSection import (
    HistoryActiveSection,
    HistoryActiveSectionAddAvgTurnDurationMs,
    HistoryActiveSectionAddCurrentTurnNumber,
    HistoryActiveSectionAddHeader,
    HistoryActiveSectionAddLastActivityMs,
    HistoryActiveSectionAddOldestTurnNumber,
    HistoryActiveSectionAddSessionStartMs,
    HistoryActiveSectionAddTotalResponseTokens,
    HistoryActiveSectionAddTotalUserTokens,
    HistoryActiveSectionAddTurns,
    HistoryActiveSectionEnd,
    HistoryActiveSectionStart,
    HistoryActiveSectionStartTurnsVector,
)

# -----------------------------------------------------------------------------
# HistoryRecentSection - Type + Builder Functions
# -----------------------------------------------------------------------------
from .HistoryRecentSection import (
    HistoryRecentSection,
    HistoryRecentSectionAddArchivedTurnIds,
    HistoryRecentSectionAddBytesEvictedTotal,
    HistoryRecentSectionAddCompressedTurns,
    HistoryRecentSectionAddEvictionPriority,
    HistoryRecentSectionAddHeader,
    HistoryRecentSectionAddLastEvictionMs,
    HistoryRecentSectionAddNewestCompressedTurn,
    HistoryRecentSectionAddNewestSummarizedTurn,
    HistoryRecentSectionAddOldestCompressedTurn,
    HistoryRecentSectionAddOldestSummarizedTurn,
    HistoryRecentSectionAddSessionSummary,
    HistoryRecentSectionAddSummarizedTurns,
    HistoryRecentSectionAddTotalTurnsArchived,
    HistoryRecentSectionEnd,
    HistoryRecentSectionStart,
    HistoryRecentSectionStartArchivedTurnIdsVector,
    HistoryRecentSectionStartCompressedTurnsVector,
    HistoryRecentSectionStartSummarizedTurnsVector,
)

# -----------------------------------------------------------------------------
# HotCore - Type
# -----------------------------------------------------------------------------
from .HotCore import HotCore

# -----------------------------------------------------------------------------
# IntentClassification - Type
# -----------------------------------------------------------------------------
from .IntentClassification import IntentClassification

# -----------------------------------------------------------------------------
# InteractionStyle - Enum
# -----------------------------------------------------------------------------
from .InteractionStyle import InteractionStyle

# -----------------------------------------------------------------------------
# LatencyMetrics - Type + Builder Functions
# -----------------------------------------------------------------------------
from .LatencyMetrics import (
    LatencyMetrics,
    LatencyMetricsAddMaxMs,
    LatencyMetricsAddMinMs,
    LatencyMetricsAddModelLatencyP50Ms,
    LatencyMetricsAddOrchestrationLatencyP50Ms,
    LatencyMetricsAddP50Ms,
    LatencyMetricsAddP90Ms,
    LatencyMetricsAddP95Ms,
    LatencyMetricsAddP99Ms,
    LatencyMetricsAddRetrievalLatencyP50Ms,
    LatencyMetricsAddToolLatencyP50Ms,
    LatencyMetricsEnd,
    LatencyMetricsStart,
)

# -----------------------------------------------------------------------------
# MemoryUsage - Type + Builder Functions
# -----------------------------------------------------------------------------
from .MemoryUsage import (
    MemoryUsage,
    MemoryUsageAddColdReferences,
    MemoryUsageAddEvictionCount,
    MemoryUsageAddHotAffectiveNow,
    MemoryUsageAddHotBeliefsActive,
    MemoryUsageAddHotBudget,
    MemoryUsageAddHotClarifications,
    MemoryUsageAddHotControl,
    MemoryUsageAddHotHistoryActive,
    MemoryUsageAddHotMeta,
    MemoryUsageAddHotNarrativeActive,
    MemoryUsageAddHotScoreboard,
    MemoryUsageAddHotTotal,
    MemoryUsageAddIsOverBudget,
    MemoryUsageAddLastEviction,
    MemoryUsageAddPressureLevel,
    MemoryUsageAddRemoteReferences,
    MemoryUsageAddSessionTotal,
    MemoryUsageAddTotalBudget,
    MemoryUsageAddWarmBeliefsHistory,
    MemoryUsageAddWarmBudget,
    MemoryUsageAddWarmHistoryRecent,
    MemoryUsageAddWarmPersona,
    MemoryUsageAddWarmTelemetry,
    MemoryUsageAddWarmTotal,
    MemoryUsageEnd,
    MemoryUsageStart,
)

# -----------------------------------------------------------------------------
# MentionedLocation - Type + Builder Functions
# -----------------------------------------------------------------------------
from .MentionedLocation import (
    MentionedLocation,
    MentionedLocationAddConfidence,
    MentionedLocationAddEntityId,
    MentionedLocationAddLocationType,
    MentionedLocationAddRawText,
    MentionedLocationEnd,
    MentionedLocationStart,
)

# -----------------------------------------------------------------------------
# MentionedTime - Type + Builder Functions
# -----------------------------------------------------------------------------
from .MentionedTime import (
    MentionedTime,
    MentionedTimeAddConfidence,
    MentionedTimeAddIsRelative,
    MentionedTimeAddRawText,
    MentionedTimeAddResolvedMs,
    MentionedTimeEnd,
    MentionedTimeStart,
)

# -----------------------------------------------------------------------------
# MetaSection - Type + Builder Functions
# -----------------------------------------------------------------------------
from .MetaSection import (
    MetaSection,
    MetaSectionAddHeader,
    MetaSectionAddIdentity,
    MetaSectionAddIsActive,
    MetaSectionAddLifecycle,
    MetaSectionAddMemory,
    MetaSectionAddPrivacyBand,
    MetaSectionAddSessionId,
    MetaSectionAddTurnCount,
    MetaSectionAddUserId,
    MetaSectionAddVersion,
    MetaSectionEnd,
    MetaSectionStart,
)

# -----------------------------------------------------------------------------
# NarrativeActiveSection - Type + Builder Functions
# -----------------------------------------------------------------------------
from .NarrativeActiveSection import (
    NarrativeActiveSection,
    NarrativeActiveSectionAddActiveThreadCount,
    NarrativeActiveSectionAddArc,
    NarrativeActiveSectionAddArchivedThreadIds,
    NarrativeActiveSectionAddCurrentThreadId,
    NarrativeActiveSectionAddHeader,
    NarrativeActiveSectionAddPausedThreadCount,
    NarrativeActiveSectionAddPausedThreads,
    NarrativeActiveSectionAddPrimaryThread,
    NarrativeActiveSectionAddResumptionHint,
    NarrativeActiveSectionAddTotalThreadsSession,
    NarrativeActiveSectionEnd,
    NarrativeActiveSectionStart,
    NarrativeActiveSectionStartArchivedThreadIdsVector,
    NarrativeActiveSectionStartPausedThreadsVector,
)

# -----------------------------------------------------------------------------
# NarrativeArc - Type + Builder Functions
# -----------------------------------------------------------------------------
from .NarrativeArc import (
    NarrativeArc,
    NarrativeArcAddClimaxEnd,
    NarrativeArcAddClimaxTurn,
    NarrativeArcAddExpositionEnd,
    NarrativeArcAddIncitingIncidentTurn,
    NarrativeArcAddPosition,
    NarrativeArcAddProgress,
    NarrativeArcAddRisingEnd,
    NarrativeArcEnd,
    NarrativeArcStart,
)

# -----------------------------------------------------------------------------
# PerformanceSummary - Type + Builder Functions
# -----------------------------------------------------------------------------
from .PerformanceSummary import (
    PerformanceSummary,
    PerformanceSummaryAddAvgLatencyMs,
    PerformanceSummaryAddAvgResponseLength,
    PerformanceSummaryAddBudgetSlaMet,
    PerformanceSummaryAddCostPerTurn,
    PerformanceSummaryAddErrorRate,
    PerformanceSummaryAddLatencySlaMet,
    PerformanceSummaryAddToolCallRate,
    PerformanceSummaryEnd,
    PerformanceSummaryStart,
)

# -----------------------------------------------------------------------------
# PersonalityProfile - Type + Builder Functions
# -----------------------------------------------------------------------------
from .PersonalityProfile import (
    PersonalityProfile,
    PersonalityProfileAddDirectness,
    PersonalityProfileAddFormality,
    PersonalityProfileAddHumor,
    PersonalityProfileAddProfileType,
    PersonalityProfileAddTraits,
    PersonalityProfileAddVerbosity,
    PersonalityProfileAddWarmth,
    PersonalityProfileEnd,
    PersonalityProfileStart,
    PersonalityProfileStartTraitsVector,
)

# -----------------------------------------------------------------------------
# PersonalityTrait - Type + Builder Functions
# -----------------------------------------------------------------------------
from .PersonalityTrait import (
    PersonalityTrait,
    PersonalityTraitAddName,
    PersonalityTraitAddValue,
    PersonalityTraitEnd,
    PersonalityTraitStart,
)

# -----------------------------------------------------------------------------
# PersonaSection - Type + Builder Functions
# -----------------------------------------------------------------------------
from .PersonaSection import (
    PersonaSection,
    PersonaSectionAddCalibrationConfidence,
    PersonaSectionAddHeader,
    PersonaSectionAddInteractionStyle,
    PersonaSectionAddIsPersonalized,
    PersonaSectionAddLastCalibratedTurn,
    PersonaSectionAddPersonality,
    PersonaSectionAddResponsePrefs,
    PersonaSectionAddVocabulary,
    PersonaSectionAddVoice,
    PersonaSectionEnd,
    PersonaSectionStart,
    PersonaSectionStartVocabularyVector,
)

# -----------------------------------------------------------------------------
# PrivacyBand - Enum
# -----------------------------------------------------------------------------
from .PrivacyBand import PrivacyBand

# -----------------------------------------------------------------------------
# ProsodyControls - Type + Builder Functions
# -----------------------------------------------------------------------------
from .ProsodyControls import (
    ProsodyControls,
    ProsodyControlsAddAccent,
    ProsodyControlsAddLanguage,
    ProsodyControlsAddPitch,
    ProsodyControlsAddSpeakingRate,
    ProsodyControlsAddVoiceId,
    ProsodyControlsAddVolume,
    ProsodyControlsEnd,
    ProsodyControlsStart,
)

# -----------------------------------------------------------------------------
# Question - Type + Builder Functions
# -----------------------------------------------------------------------------
from .Question import (
    Question,
    QuestionAddAnsweredAtTurn,
    QuestionAddAnswerSummary,
    QuestionAddAskedAtTurn,
    QuestionAddAskedBy,
    QuestionAddId,
    QuestionAddPriority,
    QuestionAddStatus,
    QuestionAddText,
    QuestionEnd,
    QuestionStart,
)

# -----------------------------------------------------------------------------
# QuestionStatus - Enum
# -----------------------------------------------------------------------------
from .QuestionStatus import QuestionStatus

# -----------------------------------------------------------------------------
# Referent - Type + Builder Functions
# -----------------------------------------------------------------------------
from .Referent import (
    Referent,
    ReferentAddEntityId,
    ReferentAddEntityType,
    ReferentAddFirstMentionedTurn,
    ReferentAddId,
    ReferentAddLastMentionedTurn,
    ReferentAddMentionCount,
    ReferentAddSalience,
    ReferentAddText,
    ReferentEnd,
    ReferentStart,
)

# -----------------------------------------------------------------------------
# ResponsePreferences - Type + Builder Functions
# -----------------------------------------------------------------------------
from .ResponsePreferences import (
    ResponsePreferences,
    ResponsePreferencesAddExplainReasoning,
    ResponsePreferencesAddIncludeExamples,
    ResponsePreferencesAddMaxResponseLength,
    ResponsePreferencesAddStyle,
    ResponsePreferencesAddUseBulletPoints,
    ResponsePreferencesAddUseHeaders,
    ResponsePreferencesEnd,
    ResponsePreferencesStart,
)

# -----------------------------------------------------------------------------
# SafetyContext - Type + Builder Functions
# -----------------------------------------------------------------------------
from .SafetyContext import (
    SafetyContext,
    SafetyContextAddBand,
    SafetyContextAddBlockedActions,
    SafetyContextAddEscalatedAtMs,
    SafetyContextAddEscalationReason,
    SafetyContextAddRequiresConfirmation,
    SafetyContextEnd,
    SafetyContextStart,
    SafetyContextStartBlockedActionsVector,
)

# -----------------------------------------------------------------------------
# SalienceEntry - Type + Builder Functions
# -----------------------------------------------------------------------------
from .SalienceEntry import (
    SalienceEntry,
    SalienceEntryAddDecayRate,
    SalienceEntryAddEntityId,
    SalienceEntryAddScore,
    SalienceEntryEnd,
    SalienceEntryStart,
)

# -----------------------------------------------------------------------------
# SchemaVersion - Type + Builder Functions
# -----------------------------------------------------------------------------
from .SchemaVersion import (
    SchemaVersion,
    SchemaVersionAddMajor,
    SchemaVersionAddMinor,
    SchemaVersionAddPatch,
    SchemaVersionEnd,
    SchemaVersionStart,
)

# -----------------------------------------------------------------------------
# ScoreboardSection - Type + Builder Functions
# -----------------------------------------------------------------------------
from .ScoreboardSection import (
    ScoreboardSection,
    ScoreboardSectionAddCurrentTurn,
    ScoreboardSectionAddHeader,
    ScoreboardSectionAddLastUpdatedMs,
    ScoreboardSectionAddLastUserIntent,
    ScoreboardSectionAddLastUserIntentConfidence,
    ScoreboardSectionAddQudStack,
    ScoreboardSectionAddReferents,
    ScoreboardSectionAddSalienceMap,
    ScoreboardSectionAddTopicStack,
    ScoreboardSectionEnd,
    ScoreboardSectionStart,
    ScoreboardSectionStartQudStackVector,
    ScoreboardSectionStartReferentsVector,
    ScoreboardSectionStartSalienceMapVector,
    ScoreboardSectionStartTopicStackVector,
)

# -----------------------------------------------------------------------------
# SectionHeader - Type + Builder Functions
# -----------------------------------------------------------------------------
from .SectionHeader import (
    SectionHeader,
    SectionHeaderAddChecksum,
    SectionHeaderAddLastUpdatedMs,
    SectionHeaderAddSectionName,
    SectionHeaderAddSizeBytes,
    SectionHeaderAddVersion,
    SectionHeaderEnd,
    SectionHeaderStart,
)

# -----------------------------------------------------------------------------
# SessionIdentity - Type + Builder Functions
# -----------------------------------------------------------------------------
from .SessionIdentity import (
    SessionIdentity,
    SessionIdentityAddDeviceId,
    SessionIdentityAddIsAnonymous,
    SessionIdentityAddIsDemoMode,
    SessionIdentityAddPrivacyBand,
    SessionIdentityAddSessionId,
    SessionIdentityAddUserId,
    SessionIdentityEnd,
    SessionIdentityStart,
)

# -----------------------------------------------------------------------------
# SessionKernel - Type
# -----------------------------------------------------------------------------
from .SessionKernel import SessionKernel

# -----------------------------------------------------------------------------
# SessionLifecycle - Type + Builder Functions
# -----------------------------------------------------------------------------
from .SessionLifecycle import (
    SessionLifecycle,
    SessionLifecycleAddCreatedAt,
    SessionLifecycleAddExpiresAt,
    SessionLifecycleAddIdleTimeoutMs,
    SessionLifecycleAddIsActive,
    SessionLifecycleAddIsExpired,
    SessionLifecycleAddLastActivity,
    SessionLifecycleAddLastTurnId,
    SessionLifecycleAddMaxLifetimeMs,
    SessionLifecycleAddTurnCount,
    SessionLifecycleEnd,
    SessionLifecycleStart,
)

# -----------------------------------------------------------------------------
# SummarizedTurn - Type + Builder Functions
# -----------------------------------------------------------------------------
from .SummarizedTurn import (
    SummarizedTurn,
    SummarizedTurnAddArchivedToLocalCold,
    SummarizedTurnAddArchiveId,
    SummarizedTurnAddPrimaryEntity,
    SummarizedTurnAddPrimaryIntent,
    SummarizedTurnAddSummary,
    SummarizedTurnAddTimestampMs,
    SummarizedTurnAddTurnId,
    SummarizedTurnAddTurnNumber,
    SummarizedTurnEnd,
    SummarizedTurnStart,
)

# -----------------------------------------------------------------------------
# TelemetrySection - Type + Builder Functions
# -----------------------------------------------------------------------------
from .TelemetrySection import (
    TelemetrySection,
    TelemetrySectionAddCollectionStarted,
    TelemetrySectionAddCost,
    TelemetrySectionAddErrors,
    TelemetrySectionAddHeader,
    TelemetrySectionAddLastUpdated,
    TelemetrySectionAddLatency,
    TelemetrySectionAddSampleCount,
    TelemetrySectionAddSummary,
    TelemetrySectionAddTokens,
    TelemetrySectionAddTurnTimings,
    TelemetrySectionEnd,
    TelemetrySectionStart,
    TelemetrySectionStartTurnTimingsVector,
)

# -----------------------------------------------------------------------------
# ThreadState - Enum
# -----------------------------------------------------------------------------
from .ThreadState import ThreadState

# -----------------------------------------------------------------------------
# TokenMetrics - Type + Builder Functions
# -----------------------------------------------------------------------------
from .TokenMetrics import (
    TokenMetrics,
    TokenMetricsAddAvgInputPerTurn,
    TokenMetricsAddAvgOutputPerTurn,
    TokenMetricsAddEmbeddingTokens,
    TokenMetricsAddGenerationTokens,
    TokenMetricsAddInputTokens,
    TokenMetricsAddOutputTokens,
    TokenMetricsAddReasoningTokens,
    TokenMetricsAddTotalTokens,
    TokenMetricsEnd,
    TokenMetricsStart,
)

# -----------------------------------------------------------------------------
# Topic - Type + Builder Functions
# -----------------------------------------------------------------------------
from .Topic import (
    Topic,
    TopicAddFirstTurn,
    TopicAddId,
    TopicAddIsPrimary,
    TopicAddLastTurn,
    TopicAddName,
    TopicAddSalience,
    TopicEnd,
    TopicStart,
)

# -----------------------------------------------------------------------------
# TurnFull - Type + Builder Functions
# -----------------------------------------------------------------------------
from .TurnFull import (
    TurnFull,
    TurnFullAddAssistantResponse,
    TurnFullAddDurationMs,
    TurnFullAddEmotion,
    TurnFullAddEntities,
    TurnFullAddIntents,
    TurnFullAddMetadata,
    TurnFullAddResponseBytes,
    TurnFullAddTimestampMs,
    TurnFullAddTurnId,
    TurnFullAddTurnNumber,
    TurnFullAddUserMessage,
    TurnFullAddUserMessageBytes,
    TurnFullEnd,
    TurnFullStart,
    TurnFullStartEntitiesVector,
    TurnFullStartIntentsVector,
)

# -----------------------------------------------------------------------------
# TurnLock - Type + Builder Functions
# -----------------------------------------------------------------------------
from .TurnLock import (
    TurnLock,
    TurnLockAddLocked,
    TurnLockAddLockedAtMs,
    TurnLockAddLockHolder,
    TurnLockAddLockTimeoutMs,
    TurnLockAddTurnId,
    TurnLockEnd,
    TurnLockStart,
)

# -----------------------------------------------------------------------------
# TurnMetadata - Type + Builder Functions
# -----------------------------------------------------------------------------
from .TurnMetadata import (
    TurnMetadata,
    TurnMetadataAddConfidence,
    TurnMetadataAddEmotion,
    TurnMetadataAddEntities,
    TurnMetadataAddIntent,
    TurnMetadataAddProcessingTimeMs,
    TurnMetadataEnd,
    TurnMetadataStart,
    TurnMetadataStartEntitiesVector,
)

# -----------------------------------------------------------------------------
# TurnTiming - Type + Builder Functions
# -----------------------------------------------------------------------------
from .TurnTiming import (
    TurnTiming,
    TurnTimingAddDurationMs,
    TurnTimingAddHadError,
    TurnTimingAddHadToolCall,
    TurnTimingAddTokenCount,
    TurnTimingAddTurnNumber,
    TurnTimingEnd,
    TurnTimingStart,
)

# -----------------------------------------------------------------------------
# VersionInfo - Type
# -----------------------------------------------------------------------------
from .VersionInfo import VersionInfo

# -----------------------------------------------------------------------------
# VocabularyEntry - Type + Builder Functions
# -----------------------------------------------------------------------------
from .VocabularyEntry import (
    VocabularyEntry,
    VocabularyEntryAddContext,
    VocabularyEntryAddSystemTerm,
    VocabularyEntryAddUserTerm,
    VocabularyEntryEnd,
    VocabularyEntryStart,
)

# -----------------------------------------------------------------------------
# WarmTier - Type
# -----------------------------------------------------------------------------
from .WarmTier import WarmTier

# =============================================================================
# __all__ - Complete Export List
# =============================================================================
__all__ = [
    # === AffectiveNowSection Types ===
    "AffectiveNowSection",
    "AffectiveNowSectionStart",
    "AffectiveNowSectionAddHeader",
    "AffectiveNowSectionAddCurrentEmotion",
    "AffectiveNowSectionAddIntensity",
    "AffectiveNowSectionAddDimensions",
    "AffectiveNowSectionAddTrajectory",
    "AffectiveNowSectionAddRecentEmotions",
    "AffectiveNowSectionStartRecentEmotionsVector",
    "AffectiveNowSectionAddConfidence",
    "AffectiveNowSectionAddSource",
    "AffectiveNowSectionAddLastUpdatedMs",
    "AffectiveNowSectionAddLastSignificantChangeMs",
    "AffectiveNowSectionAddEmpathyNeeded",
    "AffectiveNowSectionAddCelebrationAppropriate",
    "AffectiveNowSectionEnd",
    # === Emotion Types ===
    "EmotionDimensions",
    "EmotionDimensionsStart",
    "EmotionDimensionsAddValence",
    "EmotionDimensionsAddArousal",
    "EmotionDimensionsAddDominance",
    "EmotionDimensionsEnd",
    "EmotionSnapshot",
    "EmotionSnapshotStart",
    "EmotionSnapshotAddTurnNumber",
    "EmotionSnapshotAddEmotion",
    "EmotionSnapshotAddIntensity",
    "EmotionSnapshotAddValence",
    "EmotionSnapshotAddArousal",
    "EmotionSnapshotAddTimestampMs",
    "EmotionSnapshotEnd",
    "EmotionTrajectory",
    # === Section Types ===
    "BeliefsActiveSection",
    "BeliefsActiveSectionStart",
    "BeliefsActiveSectionAddHeader",
    "BeliefsActiveSectionAddTurnId",
    "BeliefsActiveSectionAddCurrentTurnFacts",
    "BeliefsActiveSectionStartCurrentTurnFactsVector",
    "BeliefsActiveSectionAddMentionedEntities",
    "BeliefsActiveSectionStartMentionedEntitiesVector",
    "BeliefsActiveSectionAddMentionedTime",
    "BeliefsActiveSectionAddMentionedLocation",
    "BeliefsActiveSectionAddPinnedFactIds",
    "BeliefsActiveSectionStartPinnedFactIdsVector",
    "BeliefsActiveSectionAddFactCount",
    "BeliefsActiveSectionAddEntityCount",
    "BeliefsActiveSectionAddLastUpdatedMs",
    "BeliefsActiveSectionEnd",
    # === BeliefsHistorySection Types ===
    "BeliefsHistorySection",
    "BeliefsHistorySectionStart",
    "BeliefsHistorySectionAddHeader",
    "BeliefsHistorySectionAddFacts",
    "BeliefsHistorySectionStartFactsVector",
    "BeliefsHistorySectionAddEntityIndex",
    "BeliefsHistorySectionStartEntityIndexVector",
    "BeliefsHistorySectionAddTotalFacts",
    "BeliefsHistorySectionAddMaxFacts",
    "BeliefsHistorySectionAddOldestTurn",
    "BeliefsHistorySectionAddNewestTurn",
    "BeliefsHistorySectionAddNextEvictionCandidates",
    "BeliefsHistorySectionStartNextEvictionCandidatesVector",
    "BeliefsHistorySectionAddEvictionThreshold",
    "BeliefsHistorySectionAddArchivedCount",
    "BeliefsHistorySectionAddArchivePointer",
    "BeliefsHistorySectionEnd",
    # === ArchivedFact Types ===
    "ArchivedFact",
    "ArchivedFactStart",
    "ArchivedFactAddFact",
    "ArchivedFactAddOriginalTurn",
    "ArchivedFactAddLastAccessedTurn",
    "ArchivedFactAddAccessCount",
    "ArchivedFactAddDemotedAt",
    "ArchivedFactAddLruScore",
    "ArchivedFactAddIsStale",
    "ArchivedFactEnd",
    # === EntityFactIndex Types ===
    "EntityFactIndex",
    "EntityFactIndexStart",
    "EntityFactIndexAddEntityId",
    "EntityFactIndexAddFactIndices",
    "EntityFactIndexStartFactIndicesVector",
    "EntityFactIndexAddLastUpdatedTurn",
    "EntityFactIndexEnd",
    "ControlSection",
    "ControlSectionStart",
    "ControlSectionAddHeader",
    "ControlSectionAddAgentLeases",
    "ControlSectionStartAgentLeasesVector",
    "ControlSectionAddFlowState",
    "ControlSectionAddTurnLock",
    "ControlSectionAddIntents",
    "ControlSectionAddDomains",
    "ControlSectionAddSafety",
    "ControlSectionAddNeverEvict",
    "ControlSectionEnd",
    "ScoreboardSection",
    "ScoreboardSectionStart",
    "ScoreboardSectionAddHeader",
    "ScoreboardSectionAddReferents",
    "ScoreboardSectionStartReferentsVector",
    "ScoreboardSectionAddQudStack",
    "ScoreboardSectionStartQudStackVector",
    "ScoreboardSectionAddSalienceMap",
    "ScoreboardSectionStartSalienceMapVector",
    "ScoreboardSectionAddTopicStack",
    "ScoreboardSectionStartTopicStackVector",
    "ScoreboardSectionAddLastUserIntent",
    "ScoreboardSectionAddLastUserIntentConfidence",
    "ScoreboardSectionAddCurrentTurn",
    "ScoreboardSectionAddLastUpdatedMs",
    "ScoreboardSectionEnd",
    "HistoryActiveSection",
    "HistoryActiveSectionStart",
    "HistoryActiveSectionAddHeader",
    "HistoryActiveSectionAddTurns",
    "HistoryActiveSectionStartTurnsVector",
    "HistoryActiveSectionAddCurrentTurnNumber",
    "HistoryActiveSectionAddOldestTurnNumber",
    "HistoryActiveSectionAddSessionStartMs",
    "HistoryActiveSectionAddLastActivityMs",
    "HistoryActiveSectionAddTotalUserTokens",
    "HistoryActiveSectionAddTotalResponseTokens",
    "HistoryActiveSectionAddAvgTurnDurationMs",
    "HistoryActiveSectionEnd",
    # === HistoryRecentSection Types ===
    "HistoryRecentSection",
    "HistoryRecentSectionStart",
    "HistoryRecentSectionAddHeader",
    "HistoryRecentSectionAddCompressedTurns",
    "HistoryRecentSectionStartCompressedTurnsVector",
    "HistoryRecentSectionAddSummarizedTurns",
    "HistoryRecentSectionStartSummarizedTurnsVector",
    "HistoryRecentSectionAddSessionSummary",
    "HistoryRecentSectionAddArchivedTurnIds",
    "HistoryRecentSectionStartArchivedTurnIdsVector",
    "HistoryRecentSectionAddTotalTurnsArchived",
    "HistoryRecentSectionAddOldestCompressedTurn",
    "HistoryRecentSectionAddNewestCompressedTurn",
    "HistoryRecentSectionAddOldestSummarizedTurn",
    "HistoryRecentSectionAddNewestSummarizedTurn",
    "HistoryRecentSectionAddEvictionPriority",
    "HistoryRecentSectionAddLastEvictionMs",
    "HistoryRecentSectionAddBytesEvictedTotal",
    "HistoryRecentSectionEnd",
    # === CompressedTurn Types ===
    "CompressedTurn",
    "CompressedTurnStart",
    "CompressedTurnAddTurnId",
    "CompressedTurnAddTurnNumber",
    "CompressedTurnAddEntities",
    "CompressedTurnStartEntitiesVector",
    "CompressedTurnAddIntents",
    "CompressedTurnStartIntentsVector",
    "CompressedTurnAddKeyPhrases",
    "CompressedTurnStartKeyPhrasesVector",
    "CompressedTurnAddTimestampMs",
    "CompressedTurnAddEmotion",
    "CompressedTurnAddUserTokens",
    "CompressedTurnAddResponseTokens",
    "CompressedTurnAddArchivedToLocalCold",
    "CompressedTurnAddArchiveId",
    "CompressedTurnEnd",
    # === SummarizedTurn Types ===
    "SummarizedTurn",
    "SummarizedTurnStart",
    "SummarizedTurnAddTurnId",
    "SummarizedTurnAddTurnNumber",
    "SummarizedTurnAddSummary",
    "SummarizedTurnAddTimestampMs",
    "SummarizedTurnAddPrimaryIntent",
    "SummarizedTurnAddPrimaryEntity",
    "SummarizedTurnAddArchivedToLocalCold",
    "SummarizedTurnAddArchiveId",
    "SummarizedTurnEnd",
    # === MetaSection Types ===
    "MetaSection",
    "MetaSectionStart",
    "MetaSectionAddHeader",
    "MetaSectionAddIdentity",
    "MetaSectionAddLifecycle",
    "MetaSectionAddMemory",
    "MetaSectionAddVersion",
    "MetaSectionAddSessionId",
    "MetaSectionAddUserId",
    "MetaSectionAddPrivacyBand",
    "MetaSectionAddTurnCount",
    "MetaSectionAddIsActive",
    "MetaSectionEnd",
    # === SessionIdentity Types ===
    "SessionIdentity",
    "SessionIdentityStart",
    "SessionIdentityAddSessionId",
    "SessionIdentityAddUserId",
    "SessionIdentityAddDeviceId",
    "SessionIdentityAddPrivacyBand",
    "SessionIdentityAddIsAnonymous",
    "SessionIdentityAddIsDemoMode",
    "SessionIdentityEnd",
    # === SessionLifecycle Types ===
    "SessionLifecycle",
    "SessionLifecycleStart",
    "SessionLifecycleAddCreatedAt",
    "SessionLifecycleAddLastActivity",
    "SessionLifecycleAddExpiresAt",
    "SessionLifecycleAddTurnCount",
    "SessionLifecycleAddLastTurnId",
    "SessionLifecycleAddIsActive",
    "SessionLifecycleAddIsExpired",
    "SessionLifecycleAddIdleTimeoutMs",
    "SessionLifecycleAddMaxLifetimeMs",
    "SessionLifecycleEnd",
    # === MemoryUsage Types ===
    "MemoryUsage",
    "MemoryUsageStart",
    "MemoryUsageAddHotControl",
    "MemoryUsageAddHotBeliefsActive",
    "MemoryUsageAddHotScoreboard",
    "MemoryUsageAddHotHistoryActive",
    "MemoryUsageAddHotClarifications",
    "MemoryUsageAddHotAffectiveNow",
    "MemoryUsageAddHotNarrativeActive",
    "MemoryUsageAddHotMeta",
    "MemoryUsageAddHotTotal",
    "MemoryUsageAddWarmBeliefsHistory",
    "MemoryUsageAddWarmHistoryRecent",
    "MemoryUsageAddWarmPersona",
    "MemoryUsageAddWarmTelemetry",
    "MemoryUsageAddWarmTotal",
    "MemoryUsageAddSessionTotal",
    "MemoryUsageAddColdReferences",
    "MemoryUsageAddRemoteReferences",
    "MemoryUsageAddHotBudget",
    "MemoryUsageAddWarmBudget",
    "MemoryUsageAddTotalBudget",
    "MemoryUsageAddIsOverBudget",
    "MemoryUsageAddPressureLevel",
    "MemoryUsageAddLastEviction",
    "MemoryUsageAddEvictionCount",
    "MemoryUsageEnd",
    # === SectionHeader Types ===
    "SectionHeader",
    "SectionHeaderStart",
    "SectionHeaderAddSectionName",
    "SectionHeaderAddVersion",
    "SectionHeaderAddSizeBytes",
    "SectionHeaderAddLastUpdatedMs",
    "SectionHeaderAddChecksum",
    "SectionHeaderEnd",
    # === Agent Types ===
    "AgentLease",
    "AgentLeaseStart",
    "AgentLeaseAddAgentId",
    "AgentLeaseAddAgentType",
    "AgentLeaseAddState",
    "AgentLeaseAddLeaseStartedMs",
    "AgentLeaseAddLeaseExpiresMs",
    "AgentLeaseAddCapabilities",
    "AgentLeaseStartCapabilitiesVector",
    "AgentLeaseAddPriority",
    "AgentLeaseEnd",
    "AgentState",
    # === Flow Types ===
    "FlowState",
    "FlowStateStart",
    "FlowStateAddCurrentPhase",
    "FlowStateAddTurnId",
    "FlowStateAddStartedAtMs",
    "FlowStateAddTimeoutMs",
    "FlowStateAddPendingAgents",
    "FlowStateStartPendingAgentsVector",
    "FlowStateAddCompletedAgents",
    "FlowStateStartCompletedAgentsVector",
    "FlowStateEnd",
    "FlowPhase",
    "TurnLock",
    "TurnLockStart",
    "TurnLockAddLocked",
    "TurnLockAddLockHolder",
    "TurnLockAddLockedAtMs",
    "TurnLockAddLockTimeoutMs",
    "TurnLockAddTurnId",
    "TurnLockEnd",
    # === Domain & Safety Types ===
    "DomainContext",
    "DomainContextStart",
    "DomainContextAddPrimaryDomain",
    "DomainContextAddActiveDomains",
    "DomainContextStartActiveDomainsVector",
    "DomainContextEnd",
    "SafetyContext",
    "SafetyContextStart",
    "SafetyContextAddBand",
    "SafetyContextAddEscalationReason",
    "SafetyContextAddEscalatedAtMs",
    "SafetyContextAddRequiresConfirmation",
    "SafetyContextAddBlockedActions",
    "SafetyContextStartBlockedActionsVector",
    "SafetyContextEnd",
    "PrivacyBand",
    # === Fact & Entity Types ===
    "Fact",
    "FactStart",
    "FactAddId",
    "FactAddSubject",
    "FactAddPredicate",
    "FactAddObject",
    "FactAddConfidence",
    "FactAddSource",
    "FactAddTimestampMs",
    "FactAddPrivacyBand",
    "FactEnd",
    "EntityRef",
    "EntityRefStart",
    "EntityRefAddId",
    "EntityRefAddType",
    "EntityRefAddDisplayName",
    "EntityRefAddConfidence",
    "EntityRefEnd",
    "MentionedTime",
    "MentionedTimeStart",
    "MentionedTimeAddRawText",
    "MentionedTimeAddResolvedMs",
    "MentionedTimeAddConfidence",
    "MentionedTimeAddIsRelative",
    "MentionedTimeEnd",
    "MentionedLocation",
    "MentionedLocationStart",
    "MentionedLocationAddRawText",
    "MentionedLocationAddLocationType",
    "MentionedLocationAddEntityId",
    "MentionedLocationAddConfidence",
    "MentionedLocationEnd",
    # === Scoreboard Types ===
    "Referent",
    "ReferentStart",
    "ReferentAddId",
    "ReferentAddText",
    "ReferentAddEntityId",
    "ReferentAddEntityType",
    "ReferentAddSalience",
    "ReferentAddFirstMentionedTurn",
    "ReferentAddLastMentionedTurn",
    "ReferentAddMentionCount",
    "ReferentEnd",
    "Question",
    "QuestionStart",
    "QuestionAddId",
    "QuestionAddText",
    "QuestionAddStatus",
    "QuestionAddAskedBy",
    "QuestionAddAskedAtTurn",
    "QuestionAddAnsweredAtTurn",
    "QuestionAddAnswerSummary",
    "QuestionAddPriority",
    "QuestionEnd",
    "QuestionStatus",
    "SalienceEntry",
    "SalienceEntryStart",
    "SalienceEntryAddEntityId",
    "SalienceEntryAddScore",
    "SalienceEntryAddDecayRate",
    "SalienceEntryEnd",
    "Topic",
    "TopicStart",
    "TopicAddId",
    "TopicAddName",
    "TopicAddSalience",
    "TopicAddFirstTurn",
    "TopicAddLastTurn",
    "TopicAddIsPrimary",
    "TopicEnd",
    "IntentClassification",
    # === Turn Types ===
    "TurnFull",
    "TurnFullStart",
    "TurnFullAddTurnId",
    "TurnFullAddTurnNumber",
    "TurnFullAddUserMessage",
    "TurnFullAddAssistantResponse",
    "TurnFullAddTimestampMs",
    "TurnFullAddDurationMs",
    "TurnFullAddMetadata",
    "TurnFullAddEntities",
    "TurnFullStartEntitiesVector",
    "TurnFullAddIntents",
    "TurnFullStartIntentsVector",
    "TurnFullAddEmotion",
    "TurnFullAddUserMessageBytes",
    "TurnFullAddResponseBytes",
    "TurnFullEnd",
    "TurnMetadata",
    "TurnMetadataStart",
    "TurnMetadataAddIntent",
    "TurnMetadataAddEntities",
    "TurnMetadataStartEntitiesVector",
    "TurnMetadataAddEmotion",
    "TurnMetadataAddConfidence",
    "TurnMetadataAddProcessingTimeMs",
    "TurnMetadataEnd",
    # === Schema Types ===
    "SchemaVersion",
    "SchemaVersionStart",
    "SchemaVersionAddMajor",
    "SchemaVersionAddMinor",
    "SchemaVersionAddPatch",
    "SchemaVersionEnd",
    # === Kernel Types ===
    "SessionKernel",
    "HotCore",
    "WarmTier",
    "VersionInfo",
    # === NarrativeActiveSection Types ===
    "NarrativeActiveSection",
    "NarrativeActiveSectionStart",
    "NarrativeActiveSectionAddHeader",
    "NarrativeActiveSectionAddPrimaryThread",
    "NarrativeActiveSectionAddPausedThreads",
    "NarrativeActiveSectionStartPausedThreadsVector",
    "NarrativeActiveSectionAddTotalThreadsSession",
    "NarrativeActiveSectionAddActiveThreadCount",
    "NarrativeActiveSectionAddPausedThreadCount",
    "NarrativeActiveSectionAddArc",
    "NarrativeActiveSectionAddCurrentThreadId",
    "NarrativeActiveSectionAddResumptionHint",
    "NarrativeActiveSectionAddArchivedThreadIds",
    "NarrativeActiveSectionStartArchivedThreadIdsVector",
    "NarrativeActiveSectionEnd",
    # === NarrativeArc Types ===
    "NarrativeArc",
    "NarrativeArcStart",
    "NarrativeArcAddPosition",
    "NarrativeArcAddExpositionEnd",
    "NarrativeArcAddRisingEnd",
    "NarrativeArcAddClimaxEnd",
    "NarrativeArcAddIncitingIncidentTurn",
    "NarrativeArcAddClimaxTurn",
    "NarrativeArcAddProgress",
    "NarrativeArcEnd",
    # === ConversationThread Types ===
    "ConversationThread",
    "ConversationThreadStart",
    "ConversationThreadAddId",
    "ConversationThreadAddTitle",
    "ConversationThreadAddState",
    "ConversationThreadAddStartedTurn",
    "ConversationThreadAddLastActiveTurn",
    "ConversationThreadAddResolvedTurn",
    "ConversationThreadAddGoal",
    "ConversationThreadAddIsGoalMet",
    "ConversationThreadAddRelatedEntities",
    "ConversationThreadStartRelatedEntitiesVector",
    "ConversationThreadAddRelatedIntents",
    "ConversationThreadStartRelatedIntentsVector",
    "ConversationThreadAddResumptionHint",
    "ConversationThreadAddContextSummary",
    "ConversationThreadEnd",
    # === ThreadState Enum ===
    "ThreadState",
    # === PersonaSection Types ===
    "PersonaSection",
    "PersonaSectionStart",
    "PersonaSectionAddHeader",
    "PersonaSectionAddPersonality",
    "PersonaSectionAddVoice",
    "PersonaSectionAddVocabulary",
    "PersonaSectionStartVocabularyVector",
    "PersonaSectionAddResponsePrefs",
    "PersonaSectionAddInteractionStyle",
    "PersonaSectionAddIsPersonalized",
    "PersonaSectionAddLastCalibratedTurn",
    "PersonaSectionAddCalibrationConfidence",
    "PersonaSectionEnd",
    # === PersonalityProfile Types ===
    "PersonalityProfile",
    "PersonalityProfileStart",
    "PersonalityProfileAddTraits",
    "PersonalityProfileStartTraitsVector",
    "PersonalityProfileAddWarmth",
    "PersonalityProfileAddFormality",
    "PersonalityProfileAddVerbosity",
    "PersonalityProfileAddHumor",
    "PersonalityProfileAddDirectness",
    "PersonalityProfileAddProfileType",
    "PersonalityProfileEnd",
    # === PersonalityTrait Types ===
    "PersonalityTrait",
    "PersonalityTraitStart",
    "PersonalityTraitAddName",
    "PersonalityTraitAddValue",
    "PersonalityTraitEnd",
    # === ProsodyControls Types ===
    "ProsodyControls",
    "ProsodyControlsStart",
    "ProsodyControlsAddSpeakingRate",
    "ProsodyControlsAddPitch",
    "ProsodyControlsAddVolume",
    "ProsodyControlsAddVoiceId",
    "ProsodyControlsAddLanguage",
    "ProsodyControlsAddAccent",
    "ProsodyControlsEnd",
    # === ResponsePreferences Types ===
    "ResponsePreferences",
    "ResponsePreferencesStart",
    "ResponsePreferencesAddStyle",
    "ResponsePreferencesAddMaxResponseLength",
    "ResponsePreferencesAddUseBulletPoints",
    "ResponsePreferencesAddUseHeaders",
    "ResponsePreferencesAddIncludeExamples",
    "ResponsePreferencesAddExplainReasoning",
    "ResponsePreferencesEnd",
    # === VocabularyEntry Types ===
    "VocabularyEntry",
    "VocabularyEntryStart",
    "VocabularyEntryAddUserTerm",
    "VocabularyEntryAddSystemTerm",
    "VocabularyEntryAddContext",
    "VocabularyEntryEnd",
    # === InteractionStyle Enum ===
    "InteractionStyle",
    # === TelemetrySection Types ===
    "TelemetrySection",
    "TelemetrySectionStart",
    "TelemetrySectionAddHeader",
    "TelemetrySectionAddTokens",
    "TelemetrySectionAddCost",
    "TelemetrySectionAddLatency",
    "TelemetrySectionAddTurnTimings",
    "TelemetrySectionStartTurnTimingsVector",
    "TelemetrySectionAddErrors",
    "TelemetrySectionAddSummary",
    "TelemetrySectionAddCollectionStarted",
    "TelemetrySectionAddLastUpdated",
    "TelemetrySectionAddSampleCount",
    "TelemetrySectionEnd",
    # === TokenMetrics Types ===
    "TokenMetrics",
    "TokenMetricsStart",
    "TokenMetricsAddInputTokens",
    "TokenMetricsAddOutputTokens",
    "TokenMetricsAddTotalTokens",
    "TokenMetricsAddReasoningTokens",
    "TokenMetricsAddGenerationTokens",
    "TokenMetricsAddEmbeddingTokens",
    "TokenMetricsAddAvgInputPerTurn",
    "TokenMetricsAddAvgOutputPerTurn",
    "TokenMetricsEnd",
    # === CostMetrics Types ===
    "CostMetrics",
    "CostMetricsStart",
    "CostMetricsAddTotalCostMicrodollars",
    "CostMetricsAddReasoningCost",
    "CostMetricsAddGenerationCost",
    "CostMetricsAddEmbeddingCost",
    "CostMetricsAddToolCost",
    "CostMetricsAddAvgCostPerTurn",
    "CostMetricsEnd",
    # === LatencyMetrics Types ===
    "LatencyMetrics",
    "LatencyMetricsStart",
    "LatencyMetricsAddP50Ms",
    "LatencyMetricsAddP90Ms",
    "LatencyMetricsAddP95Ms",
    "LatencyMetricsAddP99Ms",
    "LatencyMetricsAddMinMs",
    "LatencyMetricsAddMaxMs",
    "LatencyMetricsAddModelLatencyP50Ms",
    "LatencyMetricsAddRetrievalLatencyP50Ms",
    "LatencyMetricsAddToolLatencyP50Ms",
    "LatencyMetricsAddOrchestrationLatencyP50Ms",
    "LatencyMetricsEnd",
    # === TurnTiming Types ===
    "TurnTiming",
    "TurnTimingStart",
    "TurnTimingAddTurnNumber",
    "TurnTimingAddDurationMs",
    "TurnTimingAddTokenCount",
    "TurnTimingAddHadError",
    "TurnTimingAddHadToolCall",
    "TurnTimingEnd",
    # === ErrorMetrics Types ===
    "ErrorMetrics",
    "ErrorMetricsStart",
    "ErrorMetricsAddTotalErrors",
    "ErrorMetricsAddTimeoutErrors",
    "ErrorMetricsAddRateLimitErrors",
    "ErrorMetricsAddModelErrors",
    "ErrorMetricsAddToolErrors",
    "ErrorMetricsAddValidationErrors",
    "ErrorMetricsAddLastErrorTurn",
    "ErrorMetricsAddLastErrorMessage",
    "ErrorMetricsAddErrorRate",
    "ErrorMetricsEnd",
    # === PerformanceSummary Types ===
    "PerformanceSummary",
    "PerformanceSummaryStart",
    "PerformanceSummaryAddAvgLatencyMs",
    "PerformanceSummaryAddErrorRate",
    "PerformanceSummaryAddCostPerTurn",
    "PerformanceSummaryAddAvgResponseLength",
    "PerformanceSummaryAddToolCallRate",
    "PerformanceSummaryAddLatencySlaMet",
    "PerformanceSummaryAddBudgetSlaMet",
    "PerformanceSummaryEnd",
]
