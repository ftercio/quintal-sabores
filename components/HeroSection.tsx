import Image from 'next/image';
import React from 'react';

export interface HeroSectionProps {
  /** URL ou caminho da imagem de fundo */
  backgroundImage?: string;
  /** Caminho do arquivo da logomarca */
  logoSrc?: string;
  /** Texto alternativo para acessibilidade da logo */
  logoAlt?: string;
  /** Largura da logo em pixels */
  logoWidth?: number;
  /** Altura da logo em pixels */
  logoHeight?: number;
  /** Título acessível H1 (invisível na tela, apenas leitores de tela/SEO) */
  accessibleTitle?: string;
  /** Texto pequeno acima do destaque */
  overlineText?: string;
  /** Destaque principal / Data do evento */
  eventDate?: string;
  /** Subtítulo / Frase de chamariz */
  tagline?: string;
  /** Rótulo do botão Call to Action */
  ctaText?: string;
  /** Link de destino do botão CTA */
  ctaHref?: string;
  /** Classes CSS adicionais para o container principal */
  className?: string;
}

export const HeroSection: React.FC<HeroSectionProps> = ({
  backgroundImage = '/assets/hero-bg.jpg',
  logoSrc = '/assets/logo.png',
  logoAlt = 'Logotipo do Festival Quintal dos Sabores',
  logoWidth = 220,
  logoHeight = 120,
  accessibleTitle = 'Festival Gastronômico Quintal dos Sabores 2026',
  overlineText = 'APRESENTA',
  eventDate = '13 E 14 DE JUNHO DE 2026',
  tagline = 'O festival que celebra a culinária das comunidades de favela e a riqueza cultural da periferia de BH.',
  ctaText = 'Ver Programação',
  ctaHref = '#programacao',
  className = '',
}) => {
  return (
    <section
      className={`relative min-h-screen w-full flex flex-col items-center justify-center text-center px-4 py-16 bg-cover bg-center bg-no-repeat overflow-hidden ${className}`}
      style={{ backgroundImage: `url('${backgroundImage}')` }}
    >
      {/* Overlay escuro para alto contraste e legibilidade WCAG AA */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-[2px]" aria-hidden="true" />

      {/* Conteúdo textual e interativo acima do overlay */}
      <div className="relative z-10 flex flex-col items-center justify-center max-w-4xl mx-auto w-full">
        {/* Título H1 visível apenas para leitores de tela e robôs de SEO */}
        <h1 className="sr-only">{accessibleTitle}</h1>

        {/* Logomarca do Evento */}
        <div className="mb-6 transition-transform duration-300 hover:scale-105">
          <Image
            src={logoSrc}
            alt={logoAlt}
            width={logoWidth}
            height={logoHeight}
            priority
            className="h-auto w-auto object-contain drop-shadow-[0_0_12px_rgba(245,184,0,0.4)]"
          />
        </div>

        {/* Overline / Apresenta */}
        <span className="text-xs md:text-sm font-semibold tracking-[0.25em] uppercase text-yellow-400 opacity-90 mb-2">
          {overlineText}
        </span>

        {/* Destaque Principal / Data */}
        <h2 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-extrabold text-white mb-4 tracking-tight leading-none drop-shadow-md">
          {eventDate}
        </h2>

        {/* Subtítulo / Frase de Chamariz */}
        <p className="text-lg md:text-xl text-gray-200 mb-8 max-w-2xl font-normal leading-relaxed text-balance">
          {tagline}
        </p>

        {/* Call to Action (CTA) */}
        <a
          href={ctaHref}
          className="inline-flex items-center justify-center bg-red-600 hover:bg-red-700 active:bg-red-800 text-white font-bold text-lg px-8 py-4 rounded-xl shadow-lg hover:shadow-red-600/30 transition-all duration-200 transform hover:-translate-y-0.5 focus:outline-none focus:ring-4 focus:ring-red-500/50"
        >
          {ctaText}
        </a>
      </div>
    </section>
  );
};

export default HeroSection;
