// src/components/student/FlashcardReview.tsx
//
// Focused flashcard review overlay. Shows one card at a time with flip
// animation and simple self-assessment buttons.

import { useState, useEffect, useCallback, useRef } from 'react';
import { X, ChevronLeft, ChevronRight, RotateCcw } from 'lucide-react';
import { cn } from '../../lib/utils';
import type { Flashcard } from '../../types/studySummary';

interface FlashcardReviewProps {
  cards: Flashcard[];
  onClose: () => void;
}

type Rating = 'again' | 'hard' | 'good' | 'easy';

interface CardResult {
  index: number;
  rating: Rating;
}

export function FlashcardReview({ cards, onClose }: FlashcardReviewProps) {
  const [activeCards, setActiveCards] = useState(cards);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [hasRated, setHasRated] = useState(false);
  const [results, setResults] = useState<CardResult[]>([]);
  const [isComplete, setIsComplete] = useState(false);
  const [reviewAgainCards, setReviewAgainCards] = useState<Flashcard[]>([]);
  const [round, setRound] = useState(1);

  // Touch swipe state
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);

  const currentCard = activeCards[currentIndex];
  const progress = ((currentIndex + 1) / activeCards.length) * 100;

  const flip = useCallback(() => {
    setIsFlipped((prev) => !prev);
  }, []);

  const rate = useCallback(
    (rating: Rating) => {
      setResults((prev) => [...prev, { index: currentIndex, rating }]);
      setHasRated(true);

      // Auto-advance after a brief pause
      setTimeout(() => {
        if (currentIndex < activeCards.length - 1) {
          setCurrentIndex((prev) => prev + 1);
          setIsFlipped(false);
          setHasRated(false);
        } else {
          // All cards reviewed
          const allResults = [...results, { index: currentIndex, rating }];
          const again = allResults
            .filter((r) => r.rating === 'again')
            .map((r) => activeCards[r.index]);
          setReviewAgainCards(again);
          setIsComplete(true);
        }
      }, 300);
    },
    [currentIndex, activeCards, results],
  );

  const goToPrev = useCallback(() => {
    if (currentIndex > 0) {
      setCurrentIndex((prev) => prev - 1);
      setIsFlipped(false);
      setHasRated(false);
    }
  }, [currentIndex]);

  const goToNext = useCallback(() => {
    if (currentIndex < activeCards.length - 1) {
      setCurrentIndex((prev) => prev + 1);
      setIsFlipped(false);
      setHasRated(false);
    }
  }, [currentIndex, activeCards.length]);

  // Touch swipe handlers
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
  }, []);

  const handleTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      if (!touchStartRef.current) return;
      const dx = touchStartRef.current.x - e.changedTouches[0].clientX;
      const dy = touchStartRef.current.y - e.changedTouches[0].clientY;
      touchStartRef.current = null;

      // Only register horizontal swipes (ignore vertical scrolling)
      if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy)) return;

      if (dx > 0 && hasRated) {
        // Swipe left → next card
        goToNext();
      } else if (dx < 0) {
        // Swipe right → prev card
        goToPrev();
      }
    },
    [goToNext, goToPrev, hasRated],
  );

  // Keyboard shortcuts
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (isComplete) return;
      switch (e.key) {
        case ' ':
          e.preventDefault();
          flip();
          break;
        case 'ArrowLeft':
          e.preventDefault();
          goToPrev();
          break;
        case 'ArrowRight':
          e.preventDefault();
          if (hasRated) goToNext();
          break;
        case 'Escape':
          e.preventDefault();
          onClose();
          break;
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [flip, goToPrev, goToNext, hasRated, isComplete, onClose]);

  const restartWithAgain = () => {
    if (reviewAgainCards.length === 0) return;
    setActiveCards(reviewAgainCards);
    setCurrentIndex(0);
    setIsFlipped(false);
    setHasRated(false);
    setResults([]);
    setIsComplete(false);
    setReviewAgainCards([]);
    setRound((prev) => prev + 1);
  };

  // Completion screen
  if (isComplete) {
    const totalCards = activeCards.length;
    const againCount = reviewAgainCards.length;
    const goodCount = results.filter((r) => r.rating === 'good' || r.rating === 'easy').length;
    const hardCount = results.filter((r) => r.rating === 'hard').length;

    return (
      <div className="fixed inset-0 z-50 bg-gray-900/95 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-8 text-center">
          <div className="h-16 w-16 rounded-full bg-indigo-100 flex items-center justify-center mx-auto mb-4">
            <span className="text-2xl">&#127881;</span>
          </div>
          <h2 className="text-xl font-bold text-gray-900 mb-2">
            {round > 1 ? `Round ${round} Complete!` : 'Review Complete!'}
          </h2>
          <p className="text-sm text-gray-500 mb-6">
            You reviewed {totalCards} card{totalCards !== 1 ? 's' : ''}
          </p>

          <div className="grid grid-cols-3 gap-3 mb-6">
            <div className="bg-emerald-50 rounded-lg p-3">
              <p className="text-lg font-bold text-emerald-600">{goodCount}</p>
              <p className="text-xs text-emerald-500">Good/Easy</p>
            </div>
            <div className="bg-amber-50 rounded-lg p-3">
              <p className="text-lg font-bold text-amber-600">{hardCount}</p>
              <p className="text-xs text-amber-500">Hard</p>
            </div>
            <div className="bg-red-50 rounded-lg p-3">
              <p className="text-lg font-bold text-red-600">{againCount}</p>
              <p className="text-xs text-red-500">Again</p>
            </div>
          </div>

          <div className="space-y-2">
            {againCount > 0 && (
              <button
                onClick={restartWithAgain}
                className="w-full px-4 py-2.5 rounded-lg text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-700 transition-colors flex items-center justify-center gap-2"
              >
                <RotateCcw className="h-4 w-4" />
                Review {againCount} card{againCount !== 1 ? 's' : ''} again
              </button>
            )}
            <button
              onClick={onClose}
              className="w-full px-4 py-2.5 rounded-lg text-sm font-medium border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-gray-900/95 flex flex-col"
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4">
        <p className="text-sm font-medium text-gray-300">
          Card {currentIndex + 1} of {activeCards.length}
          {round > 1 && <span className="text-gray-500 ml-2">(Round {round})</span>}
        </p>
        <button
          onClick={onClose}
          className="p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Progress bar */}
      <div className="px-6">
        <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-indigo-500 rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Card area */}
      <div className="flex-1 flex items-center justify-center px-6 py-8">
        <div className="relative w-full max-w-lg">
          {/* Navigation arrows */}
          <button
            onClick={goToPrev}
            disabled={currentIndex === 0}
            className="absolute -left-12 top-1/2 -translate-y-1/2 p-2 rounded-full text-gray-500 hover:text-white hover:bg-gray-800 disabled:opacity-20 disabled:cursor-not-allowed transition-colors hidden md:block"
          >
            <ChevronLeft className="h-6 w-6" />
          </button>
          <button
            onClick={goToNext}
            disabled={currentIndex === activeCards.length - 1 || !hasRated}
            className="absolute -right-12 top-1/2 -translate-y-1/2 p-2 rounded-full text-gray-500 hover:text-white hover:bg-gray-800 disabled:opacity-20 disabled:cursor-not-allowed transition-colors hidden md:block"
          >
            <ChevronRight className="h-6 w-6" />
          </button>

          {/* Flashcard with flip */}
          <div
            className="cursor-pointer perspective-1000"
            onClick={flip}
            style={{ perspective: '1000px' }}
          >
            <div
              className={cn(
                'relative w-full min-h-[280px] transition-transform duration-500',
                isFlipped && '[transform:rotateY(180deg)]',
              )}
              style={{ transformStyle: 'preserve-3d' }}
            >
              {/* Front */}
              <div
                className="absolute inset-0 bg-white rounded-2xl shadow-2xl p-8 flex flex-col items-center justify-center backface-hidden"
                style={{ backfaceVisibility: 'hidden' }}
              >
                <p className="text-xs font-semibold uppercase tracking-wide text-indigo-500 mb-4">
                  Question
                </p>
                <p className="text-lg font-medium text-gray-900 text-center leading-relaxed">
                  {currentCard.front}
                </p>
                <p className="text-xs text-gray-400 mt-6">Click or press Space to flip</p>
              </div>

              {/* Back */}
              <div
                className="absolute inset-0 bg-white rounded-2xl shadow-2xl p-8 flex flex-col items-center justify-center [transform:rotateY(180deg)]"
                style={{ backfaceVisibility: 'hidden' }}
              >
                <p className="text-xs font-semibold uppercase tracking-wide text-emerald-500 mb-4">
                  Answer
                </p>
                <p className="text-lg font-medium text-gray-900 text-center leading-relaxed">
                  {currentCard.back}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Rating buttons */}
      <div className="px-6 pb-8">
        {isFlipped && !hasRated ? (
          <div className="flex items-center justify-center gap-3 max-w-lg mx-auto">
            <button
              onClick={() => rate('again')}
              className="flex-1 px-4 py-3 rounded-xl text-sm font-medium bg-red-500/90 text-white hover:bg-red-500 transition-colors"
            >
              Again
            </button>
            <button
              onClick={() => rate('hard')}
              className="flex-1 px-4 py-3 rounded-xl text-sm font-medium bg-amber-500/90 text-white hover:bg-amber-500 transition-colors"
            >
              Hard
            </button>
            <button
              onClick={() => rate('good')}
              className="flex-1 px-4 py-3 rounded-xl text-sm font-medium bg-emerald-500/90 text-white hover:bg-emerald-500 transition-colors"
            >
              Good
            </button>
            <button
              onClick={() => rate('easy')}
              className="flex-1 px-4 py-3 rounded-xl text-sm font-medium bg-indigo-500/90 text-white hover:bg-indigo-500 transition-colors"
            >
              Easy
            </button>
          </div>
        ) : (
          <p className="text-center text-sm text-gray-500">
            {hasRated ? 'Moving to next card...' : 'Flip the card to rate your recall'}
          </p>
        )}
      </div>
    </div>
  );
}
