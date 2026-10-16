import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import Providers from "@/components/Providers";
import YmTracker from "@/components/YmTracker";

const inter = Inter({ subsets: ["latin", "cyrillic"] });

const YM_SNIPPET = `(function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};m[i].l=1*new Date();for(var j=0;j<document.scripts.length;j++){if(document.scripts[j].src===r){return;}}k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})(window,document,'script','https://mc.yandex.ru/metrika/tag.js?id=113096901','ym');ym(113096901,'init',{ssr:true,defer:true,webvisor:true,clickmap:true,ecommerce:"dataLayer",referrer:document.referrer,url:location.href,accurateTrackBounce:true,trackLinks:true});`;

export const metadata: Metadata = {
  title: "HOCKEY LIVE — Хоккей онлайн в прямом эфире",
  description: "Смотри хоккейные матчи КХЛ, ВХЛ, МХЛ онлайн в прямом эфире. Стриминговая платформа.",
  icons: {
    icon: [
      { url: "/favicon-32x32.png", sizes: "32x32", type: "image/png" },
      { url: "/favicon-16x16.png", sizes: "16x16", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru">
      <head>
        <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
        <script id="ym-script" dangerouslySetInnerHTML={{ __html: YM_SNIPPET }} />
      </head>
      <body className={inter.className}>
        <noscript>
          <div>
            <img src="https://mc.yandex.ru/watch/113096901" style={{ position: "absolute", left: "-9999px" }} alt="" />
          </div>
        </noscript>
        <YmTracker />
        <Providers>
          <Header />
          <main className="min-h-screen">{children}</main>
          <Footer />
        </Providers>
      </body>
    </html>
  );
}
