/* 直接掛 NodeTalk 的測試用的宿主。
   對話狀態自 2026-07-27 起活在 `useDiscussion`(篇的層級),NodeTalk 只收 props。
   這裡給的是**真的 hook**,不是假的 talk —— 那三支測試要驗的等待提示 / thinking /
   收束回報都長在 hook 與元件的接縫上,換成 stub 就等於測自己寫的假貨。 */
import { useDiscussion } from "../src/journey/useDiscussion";
import NodeTalk from "../src/lab/NodeTalk";

type Props = Omit<React.ComponentProps<typeof NodeTalk>, "talk">;

export default function TalkHost(props: Props) {
  const talk = useDiscussion(props.slug);
  return <NodeTalk {...props} talk={talk} />;
}
