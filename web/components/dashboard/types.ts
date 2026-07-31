export interface NewsRow {
  id: number
  symbol: string | null
  title: string
  source: string
  published_at: string | null
  sentiment: string
  sentiment_confidence: number | null
  url?: string | null
}
