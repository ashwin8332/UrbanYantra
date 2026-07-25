"use client"

import React, { useState, useMemo, useCallback } from "react"
import Link from "next/link"

import {
  Upload, Satellite, FileText, Activity, ChevronRight, LoaderCircle,
  BarChart3, Thermometer, Trees, Droplets, Building2, AlertTriangle,
  Zap, MapPin, ArrowUpRight, Layers, Download, RefreshCw, Eye, ArrowLeft
} from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"
import {
  BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, AreaChart, Area
} from "recharts"

const PIE_COLORS = { concrete: "#ef4444", green: "#10b981", water: "#06b6d4" }
const THERMAL_GRADIENT = ["#3b82f6", "#06b6d4", "#10b981", "#f59e0b", "#ef4444"]

function parseReportData(report: string) {
  const concreteMatch = report.match(/Concrete Area:\s*(\d+)/i)
  const greenMatch = report.match(/Green Cover:\s*(\d+)/i)
  const waterMatch = report.match(/Water Bodies:\s*(\d+)/i)
  const hotspotMatch = report.match(/Hotspots? Detected:\s*(\d+)/i)
  const heatIndexMatch = report.match(/Heat Index:\s*([\d.]+)/i)

  return {
    concrete: concreteMatch ? parseInt(concreteMatch[1]) : 45,
    green: greenMatch ? parseInt(greenMatch[1]) : 30,
    water: waterMatch ? parseInt(waterMatch[1]) : 25,
    hotspots: hotspotMatch ? parseInt(hotspotMatch[1]) : 3,
    heatIndex: heatIndexMatch ? parseFloat(heatIndexMatch[1]) : 42.5,
  }
}

function StatCard({ icon: Icon, label, value, unit, gradient, delay, desc }: {
  icon: React.ElementType; label: string; value: string | number;
  unit?: string; gradient: string; delay: number; desc?: string
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.5 }}
      className="relative group"
    >
      <div className="absolute inset-0 bg-gradient-to-br opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-2xl blur-xl"
        style={{ background: gradient }} />
      <div className="relative bg-[#141c30]/80 border border-white/[0.06] rounded-2xl p-5 backdrop-blur-sm hover:border-white/[0.12] transition-all duration-300">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: `linear-gradient(135deg, ${gradient.split(",")[0].trim()}, ${gradient.split(",")[1]?.trim() || gradient.split(",")[0].trim()})` }}>
            <Icon className="w-5 h-5 text-white" />
          </div>
          <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">{label}</span>
        </div>
        <div className="flex items-baseline gap-1">
          <span className="text-3xl font-bold text-white tabular-nums">{value}</span>
          {unit && <span className="text-sm text-slate-400 font-medium">{unit}</span>}
        </div>
        {desc && <p className="text-[11px] text-slate-500 mt-1">{desc}</p>}
      </div>
    </motion.div>
  )
}

function CustomTooltip({ active, payload, label }: any) {
  if (active && payload && payload.length) {
    return (
      <div className="bg-[#1a1a2e]/95 border border-white/[0.08] rounded-xl px-4 py-3 shadow-2xl backdrop-blur-xl">
        <p className="text-white text-sm font-medium mb-1">{label}</p>
        {payload.map((entry: any, idx: number) => (
          <p key={idx} className="text-xs" style={{ color: entry.color }}>
            {entry.name}: <span className="font-semibold">{entry.value}{entry.name.includes("Temperature") ? "°C" : "%"}</span>
          </p>
        ))}
      </div>
    )
  }
  return null
}

export default function Page() {
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [processedImage, setProcessedImage] = useState<string | null>(null)
  const [reportText, setReportText] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)

  const parsedData = useMemo(() => {
    if (!reportText) return null
    return parseReportData(reportText)
  }, [reportText])

  const compositionData = useMemo(() => {
    if (!parsedData) return []
    return [
      { name: "Concrete", value: parsedData.concrete, color: PIE_COLORS.concrete },
      { name: "Green Cover", value: parsedData.green, color: PIE_COLORS.green },
      { name: "Water Bodies", value: parsedData.water, color: PIE_COLORS.water },
    ]
  }, [parsedData])

  const riskLevel = useMemo(() => {
    if (!parsedData) return { level: "Unknown", color: "#94a3b8", gradient: "from-slate-500 to-slate-600" }
    if (parsedData.concrete > 55) return { level: "Critical", color: "#ef4444", gradient: "#ef4444, #dc2626" }
    if (parsedData.concrete > 40) return { level: "High", color: "#f59e0b", gradient: "#f59e0b, #ea580c" }
    if (parsedData.concrete > 25) return { level: "Moderate", color: "#eab308", gradient: "#eab308, #d97706" }
    return { level: "Low", color: "#10b981", gradient: "#10b981, #059669" }
  }, [parsedData])

  const tempData = useMemo(() => {
    if (!parsedData) return []
    return [
      { material: "Concrete", temperature: 58 + parsedData.concrete * 0.1, density: parsedData.concrete },
      { material: "Asphalt", temperature: 54 + parsedData.concrete * 0.08, density: Math.round(parsedData.concrete * 0.6) },
      { material: "Soil", temperature: 42 + parsedData.green * 0.05, density: Math.round((100 - parsedData.concrete - parsedData.water) * 0.5) },
      { material: "Green Cover", temperature: 28 + parsedData.green * 0.05, density: parsedData.green },
      { material: "Water", temperature: 22 + parsedData.water * 0.05, density: parsedData.water },
    ]
  }, [parsedData])

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) setFile(e.target.files[0])
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); setIsDragging(true) }, [])
  const handleDragLeave = useCallback(() => setIsDragging(false), [])
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(false)
    if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0])
  }, [])

  const resetAnalysis = useCallback(() => {
    setFile(null)
    setProcessedImage(null)
    setReportText(null)
  }, [])

  const handleAnalyze = useCallback(async () => {
    if (!file) return
    setLoading(true)
    setProcessedImage(null)
    setReportText(null)
    const formData = new FormData()
    formData.append("file", file)

    try {
      const response = await fetch("https://isro-hackathon-6h7q.onrender.com/analyze-heat", {
        method: "POST", body: formData,
      })
      if (!response.ok) throw new Error("Backend connection failed")
      const data = await response.json()
      if (data.processed_image) setProcessedImage(data.processed_image)
      else if (data.image) setProcessedImage(data.image)
      if (data.report) {
        setReportText(typeof data.report === "string" ? data.report : JSON.stringify(data.report, null, 2))
      }
    } catch {
      alert("Could not connect to the analysis server. Please try again.")
    } finally {
      setLoading(false)
    }
  }, [file])

  const downloadReport = () => {
    if (!reportText) return
    const blob = new Blob([reportText], { type: "text/plain" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url; a.download = "heat-analysis-report.txt"; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#070b15] via-[#0a1022] to-[#0e1a2e] overflow-y-auto">
      <div className="fixed inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjAiIGhlaWdodD0iNjAiIHZpZXdCb3g9IjAgMCA2MCA2MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNMCAwaDYwdjYwSDB6IiBmaWxsPSJub25lIiBzdHJva2U9InJnYmEoNTksMTMwLDI0NiwwLjA0KSIgc3Ryb2tlLXdpZHRoPSIxIi8+PC9zdmc+')] pointer-events-none" />
      <div className="fixed top-0 -left-40 w-96 h-96 bg-blue-500/5 rounded-full blur-[120px] pointer-events-none" />
      <div className="fixed bottom-0 -right-40 w-96 h-96 bg-cyan-500/5 rounded-full blur-[120px] pointer-events-none" />

      {/* Top Bar */}
      <div className="relative px-6 py-6">
        {/* Page Header */}
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
          <div className="flex items-center gap-2 text-xs text-blue-400/80 mb-2">
            <Link href="/" className="flex items-center gap-1.5 text-slate-400 hover:text-white transition-colors mr-2">
              <ArrowLeft className="w-3.5 h-3.5" />
              <span className="uppercase tracking-wider font-medium">Back to Dashboard</span>
            </Link>
            <span className="text-slate-600">|</span>
            <Layers className="w-3.5 h-3.5" />
            <span className="uppercase tracking-wider font-medium">Urban Heat Analysis</span>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-white">Heat Mitigation Analytics</h1>
              <p className="text-slate-400 text-sm mt-1">
                Upload satellite imagery to detect urban heat and receive actionable mitigation strategies.
              </p>
            </div>
            {processedImage && (
              <button onClick={resetAnalysis} className="hidden sm:flex items-center gap-2 text-xs text-slate-400 hover:text-white bg-[#141c30] border border-white/[0.06] rounded-lg px-4 py-2 transition-colors">
                <RefreshCw className="w-3.5 h-3.5" /> New Analysis
              </button>
            )}
          </div>
        </motion.div>

        {/* KPI Stats */}
        <AnimatePresence>
          {parsedData && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-6 overflow-hidden"
            >
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatCard icon={Building2} label="Concrete Density" value={parsedData.concrete} unit="%" gradient="#ef4444, #dc2626" delay={0} desc="Urban development index" />
                <StatCard icon={Trees} label="Green Cover" value={parsedData.green} unit="%" gradient="#10b981, #059669" delay={0.1} desc="Vegetation coverage" />
                <StatCard icon={Droplets} label="Water Bodies" value={parsedData.water} unit="%" gradient="#06b6d4, #0891b2" delay={0.2} desc="Surface water area" />
                <StatCard icon={AlertTriangle} label="Risk Level" value={riskLevel.level} gradient={riskLevel.gradient} delay={0.3} desc={`Heat island severity`} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Left Column */}
          <div className="lg:col-span-3 space-y-6">
            {/* Upload Card */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
              <div className="bg-[#141c30]/50 border border-white/[0.06] rounded-2xl p-6 backdrop-blur-sm">
                <div className="flex items-center gap-3 mb-5">
                  <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/15 flex items-center justify-center">
                    <Upload className="w-4 h-4 text-blue-400" />
                  </div>
                  <div>
                    <h2 className="text-sm font-semibold text-white">Upload Satellite Image</h2>
                    <p className="text-[11px] text-slate-500">Drag & drop or click to browse</p>
                  </div>
                </div>

                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onClick={() => document.getElementById("satellite-upload")?.click()}
                  className={`border-2 border-dashed rounded-xl p-8 text-center transition-all duration-300 bg-[#0f1419]/50 group cursor-pointer ${
                    isDragging ? "border-blue-400/50 bg-blue-500/5" : "border-white/[0.06] hover:border-blue-400/30"
                  }`}
                >
                  <input type="file" accept="image/*" onChange={handleFileChange} className="hidden" id="satellite-upload" />
                  {file ? (
                    <div className="flex flex-col items-center gap-3">
                      <div className="w-12 h-12 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                        <FileText className="w-5 h-5 text-emerald-400" />
                      </div>
                      <div>
                        <p className="text-sm text-emerald-400 font-medium truncate max-w-[240px]">{file.name}</p>
                        <p className="text-xs text-slate-500 mt-1">{(file.size / 1024 / 1024).toFixed(1)} MB &middot; Click to change</p>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-3">
                      <div className="w-14 h-14 rounded-full bg-gradient-to-br from-blue-500/10 to-cyan-500/10 border border-blue-500/20 flex items-center justify-center group-hover:scale-110 transition-transform">
                        <Upload className="w-6 h-6 text-blue-400" />
                      </div>
                      <div>
                        <p className="text-sm text-slate-400">
                          Drop your image here or <span className="text-blue-400 font-medium">browse</span>
                        </p>
                        <p className="text-xs text-slate-500/60 mt-1">Supports JPG, PNG, TIFF &mdash; up to 50MB</p>
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex gap-3 mt-5">
                  <button
                    onClick={handleAnalyze}
                    disabled={!file || loading}
                    className="flex-1 bg-gradient-to-r from-blue-600 to-cyan-500 hover:from-blue-500 hover:to-cyan-400 disabled:from-slate-800 disabled:to-slate-800 disabled:text-slate-500 text-white font-medium text-sm py-3 px-4 rounded-xl transition-all duration-300 shadow-lg shadow-blue-500/15 disabled:shadow-none flex items-center justify-center gap-2"
                  >
                    {loading ? (
                      <><LoaderCircle className="w-4 h-4 animate-spin" /> Processing...</>
                    ) : (
                      <><Satellite className="w-4 h-4" /> Analyze Heat Signature <ChevronRight className="w-4 h-4" /></>
                    )}
                  </button>
                  {processedImage && (
                    <button onClick={resetAnalysis} className="sm:hidden bg-[#141c30] border border-white/[0.06] text-slate-400 hover:text-white px-4 py-3 rounded-xl transition-colors">
                      <RefreshCw className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            </motion.div>

            {/* Charts Section */}
            <AnimatePresence>
              {parsedData && (
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 20 }} className="space-y-6">
                  {/* Composition + Original Image */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="bg-[#141c30]/50 border border-white/[0.06] rounded-2xl p-6 backdrop-blur-sm">
                      <div className="flex items-center gap-2 mb-1">
                        <Zap className="w-4 h-4 text-pink-400" />
                        <h3 className="text-sm font-semibold text-white">Material Composition</h3>
                      </div>
                      <p className="text-xs text-slate-500 mb-4">Land cover distribution analysis</p>
                      <ResponsiveContainer width="100%" height={240}>
                        <PieChart>
                          <Pie data={compositionData} cx="50%" cy="50%" innerRadius={55} outerRadius={95} paddingAngle={3} dataKey="value">
                            {compositionData.map((entry, idx) => (
                              <Cell key={idx} fill={entry.color} />
                            ))}
                          </Pie>
                          <Tooltip content={<CustomTooltip />} />
                        </PieChart>
                      </ResponsiveContainer>
                      <div className="flex justify-center gap-4 mt-3">
                        {compositionData.map((item) => (
                          <div key={item.name} className="flex items-center gap-1.5 text-xs">
                            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                            <span className="text-slate-400">{item.name}</span>
                            <span className="text-white font-medium">{item.value}%</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="bg-[#141c30]/50 border border-white/[0.06] rounded-2xl p-6 backdrop-blur-sm">
                      <div className="flex items-center gap-2 mb-1">
                        <Upload className="w-4 h-4 text-blue-400" />
                        <h3 className="text-sm font-semibold text-white">Original Image</h3>
                      </div>
                      <p className="text-xs text-slate-500 mb-4">Uploaded satellite imagery</p>
                      <div className="aspect-square w-full bg-[#0f1419]/80 rounded-xl border border-white/[0.06] flex items-center justify-center overflow-hidden">
                        {file ? (
                          <img
                            src={URL.createObjectURL(file)}
                            alt="Original satellite image"
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="flex flex-col items-center gap-3 text-slate-500">
                            <Upload className="w-8 h-8 opacity-40" />
                            <p className="text-xs text-slate-500/60 text-center">No image uploaded yet</p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Temperature Distribution */}
                  <div className="bg-[#141c30]/50 border border-white/[0.06] rounded-2xl p-6 backdrop-blur-sm">
                    <div className="flex items-center gap-2 mb-1">
                      <Thermometer className="w-4 h-4 text-orange-400" />
                      <h3 className="text-sm font-semibold text-white">Surface Temperature Distribution</h3>
                    </div>
                    <p className="text-xs text-slate-500 mb-4">Heat intensity profile across material types</p>
                    <ResponsiveContainer width="100%" height={220}>
                      <AreaChart data={tempData}>
                        <defs>
                          <linearGradient id="tempGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                        <XAxis dataKey="material" stroke="#64748b" tick={{ fontSize: 11 }} />
                        <YAxis stroke="#64748b" tick={{ fontSize: 11 }} unit="°C" />
                        <Tooltip content={<CustomTooltip />} />
                        <Area type="monotone" dataKey="temperature" stroke="#ef4444" fill="url(#tempGrad)" strokeWidth={2} name="Surface Temperature" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Right Column */}
          <div className="lg:col-span-2 space-y-6">
            {/* Thermal Map */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="bg-[#141c30]/50 border border-white/[0.06] rounded-2xl p-6 backdrop-blur-sm"
            >
              <div className="flex items-center gap-3 mb-5">
                <div className="w-8 h-8 rounded-lg bg-orange-500/10 border border-orange-500/15 flex items-center justify-center">
                  <Satellite className="w-4 h-4 text-orange-400" />
                </div>
                <div className="flex-1">
                  <h2 className="text-sm font-semibold text-white">Thermal Heat Map</h2>
                  <p className="text-[11px] text-slate-500">False-color thermal intensity visualization</p>
                </div>
                {processedImage && (
                  <button onClick={downloadReport} className="w-7 h-7 rounded-lg bg-slate-800/50 border border-white/[0.06] flex items-center justify-center hover:bg-slate-700 transition-colors">
                    <Download className="w-3.5 h-3.5 text-slate-400" />
                  </button>
                )}
              </div>

              <div className="aspect-[4/3] w-full bg-[#0f1419]/80 rounded-xl border border-white/[0.06] flex items-center justify-center overflow-hidden relative group">
                {processedImage ? (
                  <>
                    <img
                      src={processedImage.startsWith("data:") ? processedImage : `data:image/jpeg;base64,${processedImage}`}
                      alt="Thermal Map"
                      className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                    />
                    <div className="absolute bottom-3 left-3 flex gap-2">
                      <span className="px-2.5 py-1 bg-black/60 backdrop-blur-sm rounded-full text-xs text-white border border-white/10 flex items-center gap-1.5">
                        <Eye className="w-3 h-3" /> Thermal View
                      </span>
                    </div>
                    <div className="absolute bottom-3 right-3 flex items-center gap-2 bg-black/60 backdrop-blur-sm rounded-full px-3 py-1.5 border border-white/10">
                      <div className="flex gap-0.5">
                        {THERMAL_GRADIENT.map((color, i) => (
                          <div key={i} className="w-3 h-3 rounded-sm" style={{ backgroundColor: color }} />
                        ))}
                      </div>
                      <span className="text-[10px] text-white/70">Scale</span>
                    </div>
                  </>
                ) : (
                  <div className="flex flex-col items-center gap-4 text-slate-500">
                    {loading ? (
                      <div className="flex flex-col items-center gap-4">
                        <div className="relative w-16 h-16">
                          <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-blue-500 animate-spin" />
                          <div className="absolute inset-2 rounded-full border-2 border-transparent border-b-cyan-400 animate-spin" style={{ animationDirection: "reverse", animationDuration: "1s" }} />
                        </div>
                        <p className="text-xs text-slate-500 animate-pulse">Generating thermal map...</p>
                      </div>
                    ) : (
                      <>
                        <Satellite className="w-10 h-10 opacity-50" />
                        <div className="text-center">
                          <p className="text-xs font-medium text-slate-400">Awaiting Analysis</p>
                          <p className="text-[11px] text-slate-500/60 mt-1">Upload an image to begin</p>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            </motion.div>

            {/* AI Expert Assessment */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="bg-[#141c30]/50 border border-white/[0.06] rounded-2xl p-6 backdrop-blur-sm"
            >
              <div className="flex items-center gap-3 mb-5">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/15 flex items-center justify-center">
                  <FileText className="w-4 h-4 text-emerald-400" />
                </div>
                <div className="flex-1">
                  <h2 className="text-sm font-semibold text-white">AI Expert Assessment</h2>
                  {parsedData && (
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      Concrete: {parsedData.concrete}% &middot; Green: {parsedData.green}% &middot; Water: {parsedData.water}%
                    </p>
                  )}
                </div>
                {reportText && (
                  <button onClick={downloadReport} className="text-xs text-blue-400 hover:text-blue-300 font-medium flex items-center gap-1">
                    <Download className="w-3 h-3" /> Export
                  </button>
                )}
              </div>

              {reportText ? (
                <div className="relative">
                  <div className="absolute -top-3 -right-3 w-20 h-20 bg-emerald-500/5 rounded-full blur-2xl pointer-events-none" />
                  <div className="text-sm text-white leading-relaxed whitespace-pre-wrap bg-[#0f1419]/60 p-5 rounded-xl border border-white/[0.06] font-mono text-xs max-h-[280px] overflow-y-auto relative">
                    {reportText}
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center gap-3 text-slate-500 py-12">
                  <Activity className="w-8 h-8 opacity-50" />
                  <p className="text-xs text-center max-w-[200px]">
                    Upload an image and run analysis to see the AI assessment
                  </p>
                </div>
              )}
            </motion.div>
          </div>
        </div>
      </div>
    </div>
  )
}
