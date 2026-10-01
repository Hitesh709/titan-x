"use client"
import Link from "next/link"
import {ChevronLeft} from "lucide-react"
import CryptoBotPanel from "@/components/crypto/CryptoBotPanel"
export default function CryptoBotPage(){return <main className="tx-content min-h-screen p-4 lg:p-6"><div className="max-w-[1400px] mx-auto space-y-5"><Link href="/dashboard/crypto" className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-white"><ChevronLeft size={15}/> Crypto Command Center</Link><h1 className="text-3xl font-black">Crypto Strategy Executor</h1><CryptoBotPanel/></div></main>}
