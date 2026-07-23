import { useState } from 'react'
import { Check, X, Coffee, Sun, Moon, Utensils, ShoppingCart, MapPin, Star } from 'lucide-react'

const SLOT_ICONS = { breakfast: Coffee, lunch: Sun, dinner: Moon }
const SLOT_COLORS = { breakfast: '#f59e0b', lunch: '#ef4444', dinner: '#6366f1' }

export default function MealConfirmation({ meals = [], onConfirm, onReject, onAutoBook }) {
  const [confirmed, setConfirmed] = useState(new Set())
  const [rejected, setRejected] = useState(new Set())

  if (!meals || meals.length === 0) {
    return (
      <div className="panel-empty">
        <Utensils size={28} strokeWidth={1.2} />
        <p>No meals to confirm. Meal slots will appear here after planning.</p>
      </div>
    )
  }

  const handleConfirm = (idx) => {
    const next = new Set(confirmed)
    rejected.delete(idx)
    if (confirmed.has(idx)) {
      next.delete(idx)
    } else {
      next.add(idx)
    }
    setConfirmed(next)
    setRejected(new Set(rejected))
    if (onConfirm) onConfirm(idx, !confirmed.has(idx))
  }

  const handleReject = (idx) => {
    const next = new Set(rejected)
    confirmed.delete(idx)
    if (rejected.has(idx)) {
      next.delete(idx)
    } else {
      next.add(idx)
    }
    setRejected(next)
    setConfirmed(new Set(confirmed))
    if (onReject) onReject(idx, !rejected.has(idx))
  }

  const handleAutoBook = (idx) => {
    if (onAutoBook) onAutoBook(idx, meals[idx])
  }

  const confirmedCount = confirmed.size
  const totalCount = meals.length

  return (
    <div className="meal-confirmation">
      <div className="panel-heading">
        <div>
          <span className="section-index">CONFIRM MEALS</span>
          <h2>Review & confirm restaurant picks</h2>
        </div>
        <div className="confirm-stats">
          <span className="stat-badge confirm">
            <Check size={14} /> {confirmedCount} confirmed
          </span>
          <span className="stat-badge pending">
            {totalCount - confirmedCount - rejected.size} pending
          </span>
          {rejected.size > 0 && (
            <span className="stat-badge reject">
              <X size={14} /> {rejected.size} rejected
            </span>
          )}
        </div>
      </div>

      <p className="panel-desc">
        The Food Agent has selected restaurants based on your cuisine preferences, 
        meal slot proximity to activities, and budget. Confirm each pick to proceed 
        with auto-ordering.
      </p>

      <div className="meal-list">
        {meals.map((meal, idx) => {
          const SlotIcon = SLOT_ICONS[meal.slot] || Utensils
          const slotColor = SLOT_COLORS[meal.slot] || '#888'
          const isConfirmed = confirmed.has(idx)
          const isRejected = rejected.has(idx)

          return (
            <div
              key={`${meal.date}-${meal.slot}-${idx}`}
              className={`meal-card ${isConfirmed ? 'confirmed' : ''} ${isRejected ? 'rejected' : ''}`}
            >
              <div className="meal-card-header">
                <div className="meal-date-slot">
                  <span className="meal-date">{meal.date}</span>
                  <span className="meal-slot-badge" style={{ background: slotColor }}>
                    <SlotIcon size={13} />
                    {meal.slot}
                  </span>
                </div>
                <div className="meal-rating">
                  <Star size={13} fill="#f59e0b" stroke="#f59e0b" />
                  <span>{meal.popularity_score?.toFixed(1) || '—'}</span>
                </div>
              </div>

              <div className="meal-card-body">
                <h4>{meal.dish}</h4>
                <div className="meal-meta">
                  <span className="meal-restaurant">
                    <Utensils size={12} /> {meal.restaurant}
                  </span>
                  {meal.area && (
                    <span className="meal-area">
                      <MapPin size={12} /> {meal.area}
                    </span>
                  )}
                  {meal.near_activity && (
                    <span className="meal-nearby">
                      Near: {meal.near_activity}
                    </span>
                  )}
                </div>
                <div className="meal-tags">
                  <span className="dish-tag">{meal.dish_category}</span>
                  <span className="price-tag">
                    {meal.currency || 'CNY'} {meal.price}
                  </span>
                </div>
              </div>

              <div className="meal-card-actions">
                <button
                  className={`confirm-btn ${isConfirmed ? 'active' : ''}`}
                  onClick={() => handleConfirm(idx)}
                  title="Confirm this meal"
                >
                  <Check size={15} />
                  {isConfirmed ? 'Confirmed' : 'Confirm'}
                </button>
                <button
                  className={`reject-btn ${isRejected ? 'active' : ''}`}
                  onClick={() => handleReject(idx)}
                  title="Reject this meal"
                >
                  <X size={15} />
                  {isRejected ? 'Rejected' : 'Reject'}
                </button>
                {isConfirmed && (
                  <button
                    className="auto-book-btn"
                    onClick={() => handleAutoBook(idx)}
                    title="Auto-book this restaurant"
                  >
                    <ShoppingCart size={14} />
                    Order
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <style>{`
        .meal-confirmation {
          max-width: 900px;
          margin: 0 auto;
          padding: 24px 32px;
        }
        .meal-confirmation .panel-heading {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 12px;
          flex-wrap: wrap;
          gap: 12px;
        }
        .meal-confirmation .panel-desc {
          color: var(--text-secondary, #666);
          font-size: 14px;
          margin-bottom: 20px;
          line-height: 1.5;
        }
        .confirm-stats {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }
        .stat-badge {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          padding: 4px 10px;
          border-radius: 20px;
          font-size: 12px;
          font-weight: 500;
        }
        .stat-badge.confirm { background: #ecfdf5; color: #059669; }
        .stat-badge.pending { background: #fef3c7; color: #d97706; }
        .stat-badge.reject { background: #fef2f2; color: #dc2626; }
        .meal-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .meal-card {
          background: var(--card-bg, #fff);
          border: 1px solid var(--border-color, #e5e7eb);
          border-radius: 12px;
          padding: 16px;
          transition: all 0.2s;
        }
        .meal-card.confirmed {
          border-color: #059669;
          background: #f0fdf4;
        }
        .meal-card.rejected {
          border-color: #dc2626;
          background: #fef2f2;
          opacity: 0.6;
        }
        .meal-card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }
        .meal-date-slot {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .meal-date {
          font-size: 13px;
          color: var(--text-secondary, #666);
          font-weight: 500;
        }
        .meal-slot-badge {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          padding: 2px 8px;
          border-radius: 10px;
          font-size: 11px;
          color: #fff;
          font-weight: 600;
          text-transform: capitalize;
        }
        .meal-rating {
          display: flex;
          align-items: center;
          gap: 3px;
          font-size: 13px;
          color: #f59e0b;
          font-weight: 600;
        }
        .meal-card-body h4 {
          margin: 0 0 6px;
          font-size: 16px;
          color: var(--text-primary, #111);
        }
        .meal-meta {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          font-size: 12px;
          color: var(--text-secondary, #666);
          margin-bottom: 8px;
        }
        .meal-meta span {
          display: inline-flex;
          align-items: center;
          gap: 3px;
        }
        .meal-tags {
          display: flex;
          gap: 6px;
        }
        .dish-tag {
          background: #eef2ff;
          color: #4f46e5;
          padding: 2px 8px;
          border-radius: 6px;
          font-size: 11px;
          font-weight: 500;
        }
        .price-tag {
          background: #f3f4f6;
          color: #374151;
          padding: 2px 8px;
          border-radius: 6px;
          font-size: 11px;
          font-weight: 600;
        }
        .meal-card-actions {
          display: flex;
          gap: 8px;
          margin-top: 12px;
          padding-top: 12px;
          border-top: 1px solid var(--border-color, #e5e7eb);
        }
        .confirm-btn, .reject-btn, .auto-book-btn {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          padding: 6px 14px;
          border-radius: 8px;
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          border: 1px solid transparent;
          transition: all 0.15s;
        }
        .confirm-btn {
          background: #f0fdf4;
          color: #059669;
          border-color: #a7f3d0;
        }
        .confirm-btn:hover { background: #d1fae5; }
        .confirm-btn.active {
          background: #059669;
          color: #fff;
          border-color: #059669;
        }
        .reject-btn {
          background: #fef2f2;
          color: #dc2626;
          border-color: #fecaca;
        }
        .reject-btn:hover { background: #fee2e2; }
        .reject-btn.active {
          background: #dc2626;
          color: #fff;
          border-color: #dc2626;
        }
        .auto-book-btn {
          background: #eff6ff;
          color: #2563eb;
          border-color: #bfdbfe;
          margin-left: auto;
        }
        .auto-book-btn:hover { background: #dbeafe; }
        .panel-empty {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 12px;
          padding: 48px 24px;
          color: var(--text-secondary, #999);
        }
      `}</style>
    </div>
  )
}
