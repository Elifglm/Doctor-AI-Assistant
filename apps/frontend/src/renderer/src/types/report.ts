export type ReportSectionStatus = 'draft' | 'approved' | 'edited'
export type ReportConfidence = 'high' | 'medium' | 'low'
export type ReportStatus = 'DRAFT' | 'REVIEWED' | 'APPROVED' | 'FINALIZED'

export interface ReportSection {
  key: string
  title: string
  content: string
  status: ReportSectionStatus
  confidence?: ReportConfidence
}

export interface ReportContent {
  sections: ReportSection[]
  approved_sections: number
  total_sections: number
}

export interface Report {
  id: number
  session_id: number
  version: number
  status: ReportStatus
  content: ReportContent
  generation_method: string
  approved_at: string | null
  approved_by: string | null
  created_at: string
}
