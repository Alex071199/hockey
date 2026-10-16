import { redirect } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export default async function MatchRedirectPage({ params }: { params: { id: string } }) {
  try {
    const res = await fetch(`${API_URL}/api/schedule/${params.id}`);
    if (res.ok) {
      const data = await res.json();
      if (data?.league) {
        redirect(`/${data.league.toLowerCase()}/match/${params.id}`);
      }
    }
  } catch {}
  redirect("/");
}
