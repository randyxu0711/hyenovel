// 未誕生的星:目錄中間偏下,一粒緩慢呼吸的塵點——不是按鈕,是星空裡還沒亮起來的位置。
// 滑過才浮出邀請;點它(或往整片星空拖一個檔)就開始擲入。
// igniting:入場點火那一下——它就是入口風化後升起的那顆火種(同一個真物體,不畫替身)。
export default function NascentStar({ onOpen, igniting }: { onOpen: () => void; igniting?: boolean }) {
  return (
    <button className={`nascent${igniting ? " ignite" : ""}`} onClick={onOpen} aria-label="新增故事">
      <span className="nascent-spark" />
      <span className="nascent-whisper">新增故事</span>
    </button>
  );
}
