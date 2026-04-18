import type { Tag } from "../types";

type TagChipSize = "xs" | "sm" | "md";

interface TagChipProps {
  tag: Tag;
  size?: TagChipSize;
  onRemove?: (tagId: number) => void;
}

const sizeClasses: Record<TagChipSize, string> = {
  xs: "px-2 py-0.5 text-[10px]",
  sm: "px-2.5 py-0.5 text-xs",
  md: "px-3 py-1 text-xs",
};

export default function TagChip({ tag, size = "sm", onRemove }: TagChipProps) {
  return (
    <span
      style={{
        backgroundColor: tag.color + "20",
        color: tag.color,
        border: `1px solid ${tag.color}40`,
      }}
      className={`inline-flex items-center ${onRemove ? "gap-1" : ""} rounded-full font-medium ${sizeClasses[size]}`}
    >
      {tag.name}
      {onRemove && (
        <button
          onClick={() => onRemove(tag.id)}
          className="ml-0.5 opacity-60 hover:opacity-100"
          title="태그 제거"
        >
          ×
        </button>
      )}
    </span>
  );
}
