import React, { useMemo, useState } from 'react'
import { apiFetch } from '../api/client'
import TopNav from '../components/TopNav'
import Badge from '../components/Badge'
import JsonDownloadButton from '../components/JsonDownloadButton'
import { csvBlob, downloadBlob, toCsv, xlsxBlobFromRows } from '../utils/exporters'

type ProdutoRow = {
  id: number
  nome: string
  atributos_json: any
  criado_em?: string
}

type MatchMultipleRequest = {
  produto: { nome: string; atributos: Record<string, any> }
  edital_ids: number[]
  consulta: string
  model?: string | null
  use_requisitos?: boolean
  email?: string | null
}

type MatchMultipleResponse = {
  consulta?: string
  produto?: any
  results?: Array<{
    edital_id: number
    resumo_tecnico?: string
    resultado?: any
    error?: string
  }>
  email_sent?: boolean
  email_error?: string
}

type MatchItem = {
  requisito?: string
  status?: string
  confidence?: number
  matched_attribute?: string
  valor_produto?: any
  justificativa?: string
  evidence?: any
  missing_fields?: any
  suggested_fix?: string
  comparacao_tecnica?: any
  detalhes_tecnicos?: any
}

function normalizeStatus(raw: any): 'success' | 'warning' | 'danger' | 'neutral' {
  const s = String(raw ?? '').toUpperCase()
  if (s.includes('ATENDE') || s === 'SIM') return 'success'
  if (s.includes('NAO') || s.includes('NÃO')) return 'danger'
  if (s.includes('DUVID') || s.includes('PARC') || s.includes('DEPEN')) return 'warning'
  return 'neutral'
}

function calcResumo(resultado: any): { total: number; atende: number; naoAtende: number; duvida: number } {
  const items = Array.isArray(resultado) ? resultado : []
  let atende = 0
  let naoAtende = 0
  let duvida = 0
  for (const it of items) {
    const v = normalizeStatus((it as any)?.status)
    if (v === 'success') atende += 1
    else if (v === 'danger') naoAtende += 1
    else if (v === 'warning') duvida += 1
  }
  return { total: items.length, atende, naoAtende, duvida }
}

function toArray(value: any): any[] {
  if (!value) return []
  if (Array.isArray(value)) return value
  if (typeof value === 'string') return [value]
  return [value]
}

function fmtConfidence(v: any): string {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return `${Math.round(n * 100)}%`
}

function statusLabel(raw: any): string {
  const s = String(raw ?? '').trim()
  if (!s) return '—'
  return s
}

export default function Match() {
  const [produtos, setProdutos] = useState<ProdutoRow[] | null>(null)
  const [produtoId, setProdutoId] = useState<string>('')
  const [produtoNome, setProdutoNome] = useState('')
  const [atributosJson, setAtributosJson] = useState('{"portas": 24, "poe": true}')
  const [editalIds, setEditalIds] = useState('1')
  const [consulta, setConsulta] = useState('switch 24 portas poe')
  const [useRequisitos, setUseRequisitos] = useState(false)
  const [email, setEmail] = useState('alvaroscareli@gmail.com')
  const [model, setModel] = useState('')
  const [out, setOut] = useState<MatchMultipleResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const [statusFilter, setStatusFilter] = useState<'all' | 'success' | 'danger' | 'warning'>('all')
  const [minConfidence, setMinConfidence] = useState<number>(0)
  const [textQuery, setTextQuery] = useState<string>('')

  async function loadProdutos() {
    try {
      const list = await apiFetch<ProdutoRow[]>('/produtos')
      setProdutos(list)
    } catch {
      setProdutos(null)
    }
  }

  React.useEffect(() => {
    loadProdutos()
  }, [])

  function applySelectedProduto(pid: string, list: ProdutoRow[] | null) {
    setProdutoId(pid)
    if (!pid || !list) return
    const found = list.find((p) => String(p.id) === pid)
    if (!found) return
    setProdutoNome(found.nome)
    setAtributosJson(JSON.stringify(found.atributos_json ?? {}, null, 2))
  }

  async function run() {
    setError(null)
    setOut(null)
    setLoading(true)
    try {
      const attrs = JSON.parse(atributosJson)
      const ids = editalIds
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .map((s) => Number(s))
        .filter((n) => Number.isFinite(n))

      const payload: MatchMultipleRequest = {
        produto: { nome: produtoNome || 'Produto', atributos: attrs },
        edital_ids: ids,
        consulta,
        model: model.trim() || undefined,
        use_requisitos: useRequisitos,
        email: email.trim() || undefined
      }

      const res = await apiFetch<MatchMultipleResponse>('/editais/match_multiple', {
        method: 'POST',
        body: JSON.stringify(payload)
      })
      setOut(res)
    } catch (e: any) {
      setError(e?.message ?? 'Erro ao rodar match')
    } finally {
      setLoading(false)
    }
  }

  function buildRowsForEdital(r: { edital_id: number; resultado?: any }) {
    const items = Array.isArray(r.resultado) ? (r.resultado as MatchItem[]) : []
    return items.map((it) => {
      const evidence = toArray(it?.evidence).map((e) => String(e)).join(' | ')
      const missing = toArray(it?.missing_fields).map((m) => String(m)).join(', ')
      return {
        edital_id: r.edital_id,
        requisito: String(it?.requisito ?? ''),
        status: statusLabel(it?.status),
        confidence: fmtConfidence(it?.confidence),
        matched_attribute: String(it?.matched_attribute ?? ''),
        valor_produto: String(it?.valor_produto ?? ''),
        evidence,
        missing_fields: missing,
        suggested_fix: String(it?.suggested_fix ?? '')
      }
    })
  }

  function buildAllRows() {
    const results = out?.results ?? []
    const rows: Record<string, any>[] = []
    for (const r of results) rows.push(...buildRowsForEdital(r))
    return rows
  }

  async function sendEmailWithAttachment(blob: Blob, filename: string) {
    const to = email.trim()
    if (!to) {
      setError('Informe um email para envio.')
      return
    }
    setError(null)
    try {
      const form = new FormData()
      form.append('to_email', to)
      form.append('subject', 'MatchLLM - Resultado do Match')
      form.append('body_text', 'Segue o resultado em anexo (exportado pelo MatchLLM).')
      form.append('file', new File([blob], filename, { type: blob.type || 'application/octet-stream' }))
      await apiFetch('/editais/email', { method: 'POST', body: form })
    } catch (e: any) {
      setError(e?.message ?? 'Falha ao enviar email')
    }
  }

  const resultRows = useMemo(() => {
    const rows = (out?.results ?? []).map((r) => {
      const resumo = calcResumo(r.resultado)
      return {
        edital_id: r.edital_id,
        resumo_tecnico: r.resumo_tecnico,
        error: r.error,
        ...resumo
      }
    })
    return rows
  }, [out])

  const executive = useMemo(() => {
    const allResults = out?.results ?? []
    let total = 0
    let atende = 0
    let naoAtende = 0
    let duvida = 0
    const gaps: Array<{ edital_id: number; requisito: string; status: string; confidence: number }> = []

    for (const r of allResults) {
      const items = Array.isArray(r.resultado) ? (r.resultado as MatchItem[]) : []
      for (const it of items) {
        total += 1
        const variant = normalizeStatus(it?.status)
        const conf = Number(it?.confidence)
        const confN = Number.isFinite(conf) ? conf : 0
        if (variant === 'success') atende += 1
        else if (variant === 'danger') {
          naoAtende += 1
          gaps.push({ edital_id: r.edital_id, requisito: String(it?.requisito ?? '—'), status: statusLabel(it?.status), confidence: confN })
        } else if (variant === 'warning') {
          duvida += 1
          gaps.push({ edital_id: r.edital_id, requisito: String(it?.requisito ?? '—'), status: statusLabel(it?.status), confidence: confN })
        }
      }
    }

    const score = total > 0 ? atende / total : 0
    const topGaps = gaps
      .sort((a, b) => {
        // first: NAO ATENDE, then DUVIDA; within: higher confidence first
        const va = normalizeStatus(a.status) === 'danger' ? 0 : 1
        const vb = normalizeStatus(b.status) === 'danger' ? 0 : 1
        if (va !== vb) return va - vb
        return (b.confidence ?? 0) - (a.confidence ?? 0)
      })
      .slice(0, 8)

    let recomendacao = 'Sem dados suficientes para recomendação.'
    if (total > 0) {
      if (naoAtende === 0 && duvida === 0) recomendacao = 'Recomendação: avançar (produto atende aos requisitos analisados).'
      else if (naoAtende > 0) recomendacao = 'Recomendação: atenção (há requisitos não atendidos; avaliar alternativas ou adequações).'
      else recomendacao = 'Recomendação: revisar (há pontos em dúvida; coletar evidências/dados técnicos).'
    }

    return { total, atende, naoAtende, duvida, score, topGaps, recomendacao }
  }, [out])

  return (
    <div className="container">
      <TopNav title="Match Produto x Edital" subtitle="Mesmo fluxo do Streamlit" />

      <div className="card">
        <div className="layout-2col">
          <div className="panel">
            <h3>Entrada</h3>

            <div className="row">
              <div>
                <label className="small">Produto salvo (do banco)</label>
                <div className="inline">
                  <select value={produtoId} onChange={(e) => applySelectedProduto(e.target.value, produtos)}>
                    <option value="">(selecione)</option>
                    {(produtos ?? []).map((p) => (
                      <option key={p.id} value={String(p.id)}>
                        {p.nome} (id={p.id})
                      </option>
                    ))}
                  </select>
                  <button type="button" className="btn btn--secondary" onClick={loadProdutos} disabled={loading}>
                    Atualizar
                  </button>
                </div>
                <div className="small" style={{ marginTop: 6 }}>
                  Dica: cadastre pelo <strong>Dataset</strong> ou extraia via <strong>Datasheet</strong>.
                </div>
              </div>

              <div>
                <label className="small">Produto (nome)</label>
                <input value={produtoNome} onChange={(e) => setProdutoNome(e.target.value)} placeholder="ex: Switch 24p PoE" />
              </div>

              <div>
                <label className="small">Atributos (JSON)</label>
                <textarea rows={10} value={atributosJson} onChange={(e) => setAtributosJson(e.target.value)} />
              </div>

              <div>
                <label className="small">IDs de editais (separados por vírgula)</label>
                <input value={editalIds} onChange={(e) => setEditalIds(e.target.value)} placeholder="996290707, 123" />
              </div>

              <div>
                <label className="small">Consulta textual (RAG)</label>
                <input value={consulta} onChange={(e) => setConsulta(e.target.value)} placeholder="switch 24 portas poe" />
              </div>

              <div className="grid-2">
                <div>
                  <label className="small">Modelo (opcional)</label>
                  <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="ex: gpt-4.1-mini / gemini..." />
                </div>
                <div>
                  <label className="small">Email (opcional)</label>
                  <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="voce@empresa.com" />
                </div>
              </div>

              <label className="small">
                <input type="checkbox" checked={useRequisitos} onChange={(e) => setUseRequisitos(e.target.checked)} />{' '}
                Usar requisitos (mais determinístico)
              </label>

              {error && (
                <div className="small" style={{ color: '#fca5a5' }}>
                  {error}
                </div>
              )}

              <div className="inline" style={{ justifyContent: 'space-between' }}>
                <button className="btn" disabled={loading} onClick={run}>
                  {loading ? 'Rodando...' : 'Executar match'}
                </button>
                <div className="inline" style={{ gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  {out ? (
                    <>
                      <button
                        type="button"
                        className="btn btn--secondary"
                        onClick={() => {
                          const rows = buildAllRows()
                          const columns = [
                            'edital_id',
                            'requisito',
                            'status',
                            'confidence',
                            'matched_attribute',
                            'valor_produto',
                            'evidence',
                            'missing_fields',
                            'suggested_fix'
                          ]
                          const csv = toCsv(rows, columns)
                          downloadBlob(csvBlob(csv), 'match_multiple.csv')
                        }}
                      >
                        Exportar CSV
                      </button>
                      <button
                        type="button"
                        className="btn btn--secondary"
                        onClick={() => {
                          const rows = buildAllRows()
                          const columns = [
                            'edital_id',
                            'requisito',
                            'status',
                            'confidence',
                            'matched_attribute',
                            'valor_produto',
                            'evidence',
                            'missing_fields',
                            'suggested_fix'
                          ]
                          const blob = xlsxBlobFromRows([{ name: 'match', rows, columns }])
                          downloadBlob(blob, 'match_multiple.xlsx')
                        }}
                      >
                        Exportar XLSX
                      </button>
                      <button
                        type="button"
                        className="btn btn--secondary"
                        onClick={async () => {
                          const rows = buildAllRows()
                          const columns = [
                            'edital_id',
                            'requisito',
                            'status',
                            'confidence',
                            'matched_attribute',
                            'valor_produto',
                            'evidence',
                            'missing_fields',
                            'suggested_fix'
                          ]
                          const blob = xlsxBlobFromRows([{ name: 'match', rows, columns }])
                          await sendEmailWithAttachment(blob, 'match_multiple.xlsx')
                        }}
                      >
                        Enviar por email
                      </button>
                      <JsonDownloadButton data={out} filename="match_multiple.json" label="Baixar JSON" />
                    </>
                  ) : null}
                </div>
              </div>

              <div className="small">
                O resultado inclui um resumo técnico por edital e o JSON detalhado para auditoria.
              </div>
            </div>
          </div>

          <div className="panel">
            <h3>Resultado</h3>

            {!out ? (
              <div className="small">Execute um match para ver o resumo e os detalhes por edital.</div>
            ) : (
              <>
                <div className="card-sub" style={{ marginBottom: 12 }}>
                  <div className="inline" style={{ justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap' }}>
                    <div>
                      <div style={{ fontWeight: 700 }}>Executive summary</div>
                      <div className="small">Resumo rápido para engenharia e venda</div>
                    </div>
                    <div className="inline" style={{ gap: 8, flexWrap: 'wrap' }}>
                      <Badge variant="info">Score: {Math.round(executive.score * 100)}%</Badge>
                      <Badge variant="success">Atende: {executive.atende}</Badge>
                      <Badge variant="danger">Não atende: {executive.naoAtende}</Badge>
                      <Badge variant="warning">Dúvida: {executive.duvida}</Badge>
                    </div>
                  </div>

                  <div className="progress" style={{ marginTop: 10 }}>
                    <div className="progress__bar" style={{ width: `${Math.round(executive.score * 100)}%` }} />
                  </div>

                  <div className="small" style={{ marginTop: 10 }}>{executive.recomendacao}</div>

                  {executive.topGaps.length > 0 && (
                    <div style={{ marginTop: 10 }}>
                      <div className="small" style={{ marginBottom: 8 }}>Principais gaps (prioridade)</div>
                      <div className="table-wrap">
                        <table className="table">
                          <thead>
                            <tr>
                              <th>Edital</th>
                              <th>Status</th>
                              <th>Confiança</th>
                              <th>Requisito</th>
                            </tr>
                          </thead>
                          <tbody>
                            {executive.topGaps.map((g, i) => (
                              <tr key={i}>
                                <td>{g.edital_id}</td>
                                <td><Badge variant={normalizeStatus(g.status)}>{g.status}</Badge></td>
                                <td>{fmtConfidence(g.confidence)}</td>
                                <td style={{ minWidth: 320 }}>{g.requisito}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>

                {(out.email_error || out.email_sent) && (
                  <div className="inline" style={{ marginBottom: 10, gap: 8, flexWrap: 'wrap' }}>
                    {out.email_sent ? <Badge variant="success">Email enviado</Badge> : null}
                    {out.email_error ? <Badge variant="warning">Email: {out.email_error}</Badge> : null}
                  </div>
                )}

                <div className="card-sub" style={{ marginBottom: 12 }}>
                  <div className="inline" style={{ justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap' }}>
                    <div>
                      <div style={{ fontWeight: 700 }}>Filtros</div>
                      <div className="small">Refine os requisitos exibidos nas tabelas</div>
                    </div>
                  </div>

                  <div className="grid-2" style={{ marginTop: 10 }}>
                    <div>
                      <label className="small">Status</label>
                      <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as any)}>
                        <option value="all">Todos</option>
                        <option value="danger">Não atende</option>
                        <option value="warning">Dúvida</option>
                        <option value="success">Atende</option>
                      </select>
                    </div>
                    <div>
                      <label className="small">Confiança mínima</label>
                      <select value={String(minConfidence)} onChange={(e) => setMinConfidence(Number(e.target.value))}>
                        <option value="0">0%</option>
                        <option value="0.5">50%</option>
                        <option value="0.7">70%</option>
                        <option value="0.85">85%</option>
                      </select>
                    </div>
                  </div>

                  <div style={{ marginTop: 10 }}>
                    <label className="small">Buscar por texto (requisito / evidência)</label>
                    <input value={textQuery} onChange={(e) => setTextQuery(e.target.value)} placeholder="ex: poe, 24 portas, rack..." />
                  </div>
                </div>

                <div className="card-sub">
                  <div className="small" style={{ marginBottom: 8 }}>
                    Visão geral
                  </div>
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Edital</th>
                          <th>Total</th>
                          <th>Atende</th>
                          <th>Não atende</th>
                          <th>Dúvida</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {resultRows.map((r) => {
                          const hasError = Boolean(r.error)
                          const variant = hasError
                            ? 'danger'
                            : r.naoAtende > 0
                              ? 'warning'
                              : r.atende > 0
                                ? 'success'
                                : 'neutral'
                          return (
                            <tr key={r.edital_id}>
                              <td>{r.edital_id}</td>
                              <td>{r.total}</td>
                              <td>{r.atende}</td>
                              <td>{r.naoAtende}</td>
                              <td>{r.duvida}</td>
                              <td>
                                <Badge variant={variant}>
                                  {hasError ? 'Erro' : variant === 'success' ? 'OK' : variant === 'warning' ? 'Atenção' : '—'}
                                </Badge>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="stack">
                  {(out.results ?? []).map((r) => (
                    <div key={r.edital_id} className="card-sub">
                      <div className="inline" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <div style={{ fontWeight: 700 }}>Edital #{r.edital_id}</div>
                          <div className="small">Resumo técnico e evidências</div>
                        </div>
                        <div className="inline" style={{ gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                          <button
                            type="button"
                            className="btn btn--secondary"
                            onClick={() => {
                              const rows = buildRowsForEdital(r)
                              const columns = [
                                'edital_id',
                                'requisito',
                                'status',
                                'confidence',
                                'matched_attribute',
                                'valor_produto',
                                'evidence',
                                'missing_fields',
                                'suggested_fix'
                              ]
                              const csv = toCsv(rows, columns)
                              downloadBlob(csvBlob(csv), `match_edital_${r.edital_id}.csv`)
                            }}
                          >
                            CSV
                          </button>
                          <button
                            type="button"
                            className="btn btn--secondary"
                            onClick={() => {
                              const rows = buildRowsForEdital(r)
                              const columns = [
                                'edital_id',
                                'requisito',
                                'status',
                                'confidence',
                                'matched_attribute',
                                'valor_produto',
                                'evidence',
                                'missing_fields',
                                'suggested_fix'
                              ]
                              const blob = xlsxBlobFromRows([{ name: `edital_${r.edital_id}`, rows, columns }])
                              downloadBlob(blob, `match_edital_${r.edital_id}.xlsx`)
                            }}
                          >
                            XLSX
                          </button>
                          <button
                            type="button"
                            className="btn btn--secondary"
                            onClick={async () => {
                              const rows = buildRowsForEdital(r)
                              const columns = [
                                'edital_id',
                                'requisito',
                                'status',
                                'confidence',
                                'matched_attribute',
                                'valor_produto',
                                'evidence',
                                'missing_fields',
                                'suggested_fix'
                              ]
                              const blob = xlsxBlobFromRows([{ name: `edital_${r.edital_id}`, rows, columns }])
                              await sendEmailWithAttachment(blob, `match_edital_${r.edital_id}.xlsx`)
                            }}
                          >
                            Email
                          </button>
                          <JsonDownloadButton data={r} filename={`match_edital_${r.edital_id}.json`} label="JSON" />
                        </div>
                      </div>

                      {r.error ? (
                        <div className="small" style={{ color: '#fca5a5', marginTop: 10 }}>
                          {r.error}
                        </div>
                      ) : (
                        <>
                          {r.resumo_tecnico ? (
                            <p className="summary">{r.resumo_tecnico}</p>
                          ) : (
                            <p className="summary small">(sem resumo técnico)</p>
                          )}

                          <div className="small" style={{ marginTop: 10, marginBottom: 8 }}>
                            Tabela de requisitos
                          </div>

                          <div className="table-wrap">
                            <table className="table">
                              <thead>
                                <tr>
                                  <th>Requisito</th>
                                  <th>Status</th>
                                  <th>Confiança</th>
                                  <th>Atributo</th>
                                  <th>Valor do produto</th>
                                  <th>Evidência</th>
                                  <th>Campos faltando</th>
                                  <th>Sugestão</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(Array.isArray(r.resultado) ? (r.resultado as MatchItem[]) : [])
                                  .filter((it) => {
                                    const variant = normalizeStatus(it?.status)
                                    if (statusFilter !== 'all' && variant !== statusFilter) return false
                                    const conf = Number(it?.confidence)
                                    const confN = Number.isFinite(conf) ? conf : 0
                                    if (confN < minConfidence) return false
                                    const q = textQuery.trim().toLowerCase()
                                    if (!q) return true
                                    const evidence = toArray(it?.evidence).map((e) => String(e)).join(' ').toLowerCase()
                                    const req = String(it?.requisito ?? '').toLowerCase()
                                    return req.includes(q) || evidence.includes(q)
                                  })
                                  .map((it, idx) => {
                                  const variant = normalizeStatus(it?.status)
                                  const evidence = toArray(it?.evidence)
                                  const missing = toArray(it?.missing_fields)

                                  return (
                                    <tr key={idx}>
                                      <td style={{ minWidth: 220 }}>{String(it?.requisito ?? '—')}</td>
                                      <td>
                                        <Badge variant={variant}>{statusLabel(it?.status)}</Badge>
                                      </td>
                                      <td>{fmtConfidence(it?.confidence)}</td>
                                      <td style={{ minWidth: 140 }}>{String(it?.matched_attribute ?? '—')}</td>
                                      <td style={{ minWidth: 180 }}>{String(it?.valor_produto ?? '—')}</td>
                                      <td style={{ minWidth: 240 }}>
                                        {evidence.length ? evidence.map((e) => String(e)).join(' | ') : '—'}
                                      </td>
                                      <td style={{ minWidth: 200 }}>
                                        {missing.length ? missing.map((m) => String(m)).join(', ') : '—'}
                                      </td>
                                      <td style={{ minWidth: 220 }}>{String(it?.suggested_fix ?? '—')}</td>
                                    </tr>
                                  )
                                })}
                              </tbody>
                            </table>
                          </div>

                          <details style={{ marginTop: 10 }}>
                            <summary className="small">Ver JSON completo do edital</summary>
                            <pre style={{ marginTop: 10 }}>{JSON.stringify(r, null, 2)}</pre>
                          </details>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
