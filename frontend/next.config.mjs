/** @type {import('next').NextConfig} */
const nextConfig = {
  // ESLint tidak wajib untuk build; biar build cepat & tak gagal karena lint config.
  eslint: { ignoreDuringBuilds: true },
  // 'design/' adalah referensi visual statis (HTML comp) — jangan ikut di-compile.
};

export default nextConfig;
